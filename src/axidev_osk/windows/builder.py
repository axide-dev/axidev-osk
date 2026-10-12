"""Generic window builder for runtime window configs."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QCloseEvent, QHideEvent, QMoveEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from ..attachments.runtime import WindowAttachments
from ..components.pointer_locator import PointerLocator, install_pointer_locator
from ..config.models import ChromeConfig, DwellClickConfig, OverlayConfig, PointerLocatorConfig
from ..config.profile import Live, WindowConfig, WindowValues
from ..nodes import apply_style
from ..runtime.app_messages import window_close_requested, window_drag_ended, window_drag_started
from ..runtime.engine_messages import window_state_changed
from .chrome import OverlayChromeWidgets, install_overlay_chrome
from .dwell_click import DwellClickController
from .opacity import WindowOpacityController
from .overlay import configure_always_on_top_window, configure_plain_window
from .surface import RootSurface

if TYPE_CHECKING:
    from ..runtime.engine import Engine


class _WindowInputBlocker(QObject):
    """Swallow mouse input inside one window except within nodes that pass the block."""

    _BLOCKED_EVENTS = {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseMove,
        QEvent.Type.Wheel,
        QEvent.Type.ContextMenu,
    }

    def __init__(self, window: QWidget) -> None:
        # Parented to the window, so Qt drops the filter when the window is deleted.
        super().__init__(window)
        self._window = window

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Return true for blocked mouse events within the target window."""

        if event.type() not in self._BLOCKED_EVENTS or not isinstance(watched, QWidget):
            return False
        if watched.window() is not self._window:
            return False

        current: QWidget | None = watched
        while current is not None:
            if current.property("passesInputBlock"):
                return False
            if current is self._window:
                break
            current = current.parentWidget()
        return True


class RuntimeWindow(QMainWindow):
    """Generic host window around configured content.

    The class owns Qt event interception and overlay show handling, and reports
    what the window looks like on screen as ``window.state_changed``. Window
    identity, content, chrome, and overlay behavior come from config; its title,
    opacity, minimum size, input block, and style follow state through bindings.
    Closing the window never closes it directly: it sends
    ``window.close_requested`` through the queue, and the window manager closes
    windows by hiding and deleting them.
    """

    def __init__(
        self,
        *,
        window_id: str,
        overlay: OverlayConfig,
        chrome: ChromeConfig,
        values: Live[WindowValues],
        build_content: Callable[[], QWidget],
        engine: Engine,
        dwell: DwellClickConfig | None = None,
    ) -> None:
        """Create a generic runtime window around content built by ``build_content``.

        Side effects:
            Builds child widgets, configures platform overlay behavior, and
            binds the window's values to state.
        """

        super().__init__()
        self._window_id = window_id
        self._engine = engine
        self._default_close = values.initial.default_close
        self._input_blocker: _WindowInputBlocker | None = None
        self._minimum_size = values.initial.minimum_size
        self._chrome_widgets: OverlayChromeWidgets | None = None
        self._dwell_click: DwellClickController | None = None
        self._pointer_locators: dict[str, PointerLocator] = {}
        self.setProperty("componentType", "window")
        self.setProperty("componentId", window_id)
        self.setWindowTitle(values.initial.title)

        if overlay.always_on_top:
            self._overlay = configure_always_on_top_window(self, config=overlay.config)
        else:
            self._overlay = configure_plain_window(self)
        try:
            central = build_content()
            if chrome.enabled and getattr(self._overlay, "uses_custom_chrome", False):
                central_layout = central.layout()
                if isinstance(central_layout, QVBoxLayout):
                    use_runtime_drag_motion = getattr(self._overlay, "uses_runtime_pointer_drag", False)
                    self._chrome_widgets = install_overlay_chrome(
                        central_layout,
                        title=self.windowTitle(),
                        parent=central,
                        on_move=self.move_by,
                        on_resize=self._overlay.resize_by,
                        use_runtime_drag_motion=use_runtime_drag_motion,
                        on_drag_started=(
                            lambda: engine.dispatcher.dispatch(window_drag_started(window_id))
                        )
                        if use_runtime_drag_motion
                        else None,
                        on_drag_ended=(
                            lambda: engine.dispatcher.dispatch(window_drag_ended(window_id))
                        )
                        if use_runtime_drag_motion
                        else None,
                    )
            self.setCentralWidget(central)
            if dwell is not None:
                self._dwell_click = DwellClickController(self, central, dwell)
            self._opacity = WindowOpacityController(self)
            unbind = engine.bindings.bind(values.decode, f"window:{window_id}", self._apply_values, fallback=values.initial)
            self.destroyed.connect(lambda _object=None: unbind())
            self.apply_startup_size(minimum_size=self._minimum_size)
        except Exception:
            self.release_platform_resources()
            raise

    def install_pointer_locator(self, settings: PointerLocatorConfig) -> None:
        """Add pointer feedback behind this window's content."""

        central = self.centralWidget()
        assert isinstance(central, RootSurface)
        self._pointer_locators[settings.id] = install_pointer_locator(central, settings)

    def set_pointer_locator(self, settings: PointerLocatorConfig) -> None:
        """Apply new settings to an installed pointer locator."""

        locator = self._pointer_locators.get(settings.id)
        if locator is not None:
            locator.set_settings(settings)

    def set_dwell(self, config: DwellClickConfig) -> None:
        """Apply new dwell settings, including whether dwell is enabled."""

        if self._dwell_click is not None:
            self._dwell_click.set_config(config)

    @property
    def default_close(self) -> bool:
        """Whether closing this window follows the engine's close rule."""

        return self._default_close

    def _apply_values(self, values: WindowValues, previous: WindowValues | None) -> None:
        if previous is None or values.title != previous.title:
            self.setWindowTitle(values.title)
            if self._chrome_widgets is not None:
                self._chrome_widgets.title_bar.set_title(values.title)
        apply_style(self, values.style, previous.style if previous is not None else None)
        if previous is None or values.opacity != previous.opacity:
            self._opacity.set_opacity(values.opacity)
        if values.input_blocked and self._input_blocker is None:
            self._install_input_blocker()
        elif not values.input_blocked:
            self._remove_input_blocker()
        self._default_close = values.default_close
        self._minimum_size = values.minimum_size
        if previous is not None and values.minimum_size != previous.minimum_size:
            self.apply_startup_size(minimum_size=values.minimum_size)

    @property
    def window_id(self) -> str:
        """Return this window's deterministic runtime ID."""

        return self._window_id

    def _install_input_blocker(self) -> None:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("Blocking window input requires a QApplication")
        self._input_blocker = _WindowInputBlocker(self)
        app.installEventFilter(self._input_blocker)

    def _remove_input_blocker(self) -> bool:
        blocker = self._input_blocker
        if blocker is None:
            return False
        self._input_blocker = None
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(blocker)
        blocker.deleteLater()
        return True

    def move_by(self, dx: int, dy: int) -> None:
        """Move this window through its selected overlay backend."""

        self._overlay.move_by(dx, dy)
        self._report_state()

    def refresh_screen_configuration(self) -> None:
        """Apply display recovery through the selected overlay backend."""

        refresh = getattr(self._overlay, "refresh_screen_configuration", None)
        if refresh is not None:
            refresh()

    def set_close_enabled(self, enabled: bool) -> None:
        """Set whether installed custom chrome exposes its close control."""

        if self._chrome_widgets is not None:
            self._chrome_widgets.title_bar.set_close_enabled(enabled)

    def release_platform_resources(self) -> None:
        """Release native resources and the input block before Qt destroys this window."""

        self._remove_input_blocker()
        release = getattr(self._overlay, "release_resources", None)
        if release is not None:
            release()

    def apply_startup_size(self, *, minimum_size: tuple[int, int] = (0, 0)) -> None:
        """Resize the window to its polished minimum size.

        Args:
            minimum_size: Optional lower bound for startup size as ``(width, height)``.

        Returns:
            None.

        Side effects:
            Updates Qt minimum size and current size.
        """

        self.ensurePolished()
        central_widget = self.centralWidget()
        if central_widget is not None:
            central_widget.ensurePolished()
            central_layout = central_widget.layout()
            if central_layout is not None:
                central_layout.activate()
        resolved_minimum_size = self.minimumSizeHint().expandedTo(QSize(*minimum_size))
        if central_widget is not None and central_widget.hasHeightForWidth():
            # Wrapped text is taller at the final width than the size hint assumes.
            needed_height = central_widget.heightForWidth(resolved_minimum_size.width())
            resolved_minimum_size.setHeight(max(resolved_minimum_size.height(), needed_height))
        self.setMinimumSize(resolved_minimum_size)
        self.resize(resolved_minimum_size)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        """Send ``window.close_requested`` instead of closing; a removed output's close is ignored."""

        removed_output = getattr(self._overlay, "has_removed_output", None)
        if removed_output is not None and removed_output():
            event.ignore()
            return
        self._engine.dispatcher.post(window_close_requested(self._window_id))
        event.ignore()

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        """Let the overlay controller apply show-time platform fixes."""

        super().showEvent(event)
        self.apply_startup_size(minimum_size=self._minimum_size)
        self._overlay.handle_show()
        if self._dwell_click is not None:
            self._dwell_click.start()
        self._report_state()

    def hideEvent(self, event: QHideEvent) -> None:  # type: ignore[override]
        """Stop dwell sampling while this window is hidden."""

        if self._dwell_click is not None:
            self._dwell_click.stop()
        super().hideEvent(event)
        self._report_state()

    def changeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        """Report minimize and restore as window observations."""

        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._report_state()

    def moveEvent(self, event: QMoveEvent) -> None:  # type: ignore[override]
        super().moveEvent(event)
        self._report_state()

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._report_state()

    def _report_state(self) -> None:
        x, y = self._overlay.position()
        # Posted, so profile callbacks never run inside this window's Qt event handlers.
        self._engine.dispatcher.post(
            window_state_changed(
                self._window_id,
                visible=self.isVisible(),
                minimized=self.isMinimized(),
                x=x,
                y=y,
                width=self.width(),
                height=self.height(),
            )
        )


def build_profile_window(
    config: WindowConfig,
    engine: Engine,
    *,
    attachments: WindowAttachments | None = None,
) -> RuntimeWindow:
    """Build a runtime window whose content is a profile node tree.

    ``attachments`` names the dwell settings and pointer locators this window
    installs; the attachment runtime provides them and applies later changes.
    """

    installed = attachments or WindowAttachments()

    def build_content() -> QWidget:
        surface = RootSurface()
        surface.setObjectName("rootSurface")
        surface.setProperty("componentType", "surface")
        surface.setProperty("componentId", config.id)
        surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(engine.node_builder.build(config.content))
        return surface

    window = RuntimeWindow(
        window_id=config.id,
        overlay=config.overlay,
        chrome=config.chrome,
        values=config.values,
        build_content=build_content,
        engine=engine,
        dwell=installed.dwell,
    )
    for locator in installed.pointer_locators:
        window.install_pointer_locator(locator)
    return window
