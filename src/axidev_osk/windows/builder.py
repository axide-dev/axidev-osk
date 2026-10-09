"""Generic window builder for runtime window configs."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QCloseEvent, QHideEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from ..attachments.runtime import WindowAttachments
from ..components.pointer_locator import install_pointer_locator
from ..config.models import ChromeConfig, DwellClickConfig, OverlayConfig
from ..config.profile import StyleConfig, WindowConfig
from ..nodes import apply_style
from ..runtime.app_messages import window_close_requested, window_drag_ended, window_drag_started
from ..runtime.context import Context
from ..runtime.engine_messages import window_state_changed
from .chrome import OverlayChromeWidgets, install_overlay_chrome
from .dwell_click import DwellClickController
from .opacity import WindowOpacityController
from .overlay import configure_always_on_top_window, configure_plain_window
from .surface import RootSurface


class _WindowInputBlocker(QObject):
    """Swallow mouse input inside one window except within the allowed nodes."""

    _BLOCKED_EVENTS = {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseMove,
        QEvent.Type.Wheel,
        QEvent.Type.ContextMenu,
    }

    def __init__(self, window: QWidget, allowed_component_ids: frozenset[str]) -> None:
        # Parented to the window, so Qt drops the filter when the window is deleted.
        super().__init__(window)
        self._window = window
        self._allowed_component_ids = allowed_component_ids

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Return true for blocked mouse events within the target window."""

        if event.type() not in self._BLOCKED_EVENTS or not isinstance(watched, QWidget):
            return False
        if watched.window() is not self._window:
            return False

        current: QWidget | None = watched
        while current is not None:
            if current.property("componentId") in self._allowed_component_ids:
                return False
            if current is self._window:
                break
            current = current.parentWidget()
        return True


class RuntimeWindow(QMainWindow):
    """Generic host window around configured content.

    The class owns Qt event interception, overlay show handling, its opacity,
    and its input block, and reports them as ``window.state_changed``. Window
    identity, title, content, chrome, and overlay behavior all come from config.
    Closing the window never closes it directly: it sends
    ``window.close_requested`` through the queue, and the window manager closes
    windows by hiding and deleting them.
    """

    def __init__(
        self,
        *,
        window_id: str,
        title: str,
        overlay: OverlayConfig,
        chrome: ChromeConfig,
        opacity: float,
        minimum_size: tuple[int, int],
        build_content: Callable[[], QWidget],
        context: Context,
        dwell: DwellClickConfig | None = None,
        style: StyleConfig | None = None,
    ) -> None:
        """Create a generic runtime window around content built by ``build_content``.

        Side effects:
            Builds child widgets and configures platform overlay behavior.
        """

        super().__init__()
        self._window_id = window_id
        self._context = context
        self._configured_opacity = opacity
        self._current_opacity = opacity
        self._input_blocker: _WindowInputBlocker | None = None
        self._minimum_size = minimum_size
        self._chrome_widgets: OverlayChromeWidgets | None = None
        self._dwell_click: DwellClickController | None = None
        self.setProperty("componentType", "window")
        self.setProperty("componentId", window_id)
        self.setWindowTitle(title)
        if style is not None:
            apply_style(self, style)

        if overlay.always_on_top:
            self._overlay = configure_always_on_top_window(self, config=overlay.config)
        else:
            self._overlay = configure_plain_window(self)
        self.destroyed.connect(self._release_platform_resources_on_destroy)
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
                        on_move=self._overlay.move_by,
                        on_resize=self._overlay.resize_by,
                        use_runtime_drag_motion=use_runtime_drag_motion,
                        on_drag_started=(
                            lambda: context.dispatcher.dispatch(window_drag_started(window_id))
                        )
                        if use_runtime_drag_motion
                        else None,
                        on_drag_ended=(
                            lambda: context.dispatcher.dispatch(window_drag_ended(window_id))
                        )
                        if use_runtime_drag_motion
                        else None,
                    )
            self.setCentralWidget(central)
            if dwell is not None:
                self._dwell_click = DwellClickController(self, central, dwell)
                self._dwell_click.set_enabled(dwell.enabled)
            self._opacity = WindowOpacityController(self)
            self.set_visual_opacity(opacity)
            self.apply_startup_size(minimum_size=minimum_size)
        except Exception:
            self.release_platform_resources()
            raise

    @property
    def window_id(self) -> str:
        """Return this window's deterministic runtime ID."""

        return self._window_id

    @property
    def configured_opacity(self) -> float:
        """Return the opacity this window was configured with."""

        return self._configured_opacity

    @property
    def input_blocked(self) -> bool:
        """Whether pointer input is blocked outside the allowed nodes."""

        return self._input_blocker is not None

    def set_visual_opacity(self, opacity: float) -> None:
        """Set opacity through the platform-supported window implementation."""

        self._opacity.set_opacity(opacity)
        self._current_opacity = opacity
        self._report_state()

    def block_input(self, allowed_node_ids: frozenset[str]) -> None:
        """Ignore pointer input on this window except inside the allowed nodes."""

        app = QApplication.instance()
        if app is None:
            raise RuntimeError("Blocking window input requires a QApplication")
        self._remove_input_blocker()
        self._input_blocker = _WindowInputBlocker(self, allowed_node_ids)
        app.installEventFilter(self._input_blocker)
        self._report_state()

    def unblock_input(self) -> None:
        """Remove a pointer-input block installed by ``block_input``."""

        if self._remove_input_blocker():
            self._report_state()

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

    def set_dwell_enabled(self, enabled: bool) -> None:
        """Set whether pointer dwell activates components in this window."""

        if self._dwell_click is not None:
            self._dwell_click.set_enabled(enabled)

    def move_by(self, dx: int, dy: int) -> None:
        """Move this window through its selected overlay backend."""

        self._overlay.move_by(dx, dy)

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
        """Release native resources before Qt destroys this window."""

        release = getattr(self._overlay, "release_resources", None)
        if release is not None:
            release()

    def _release_platform_resources_on_destroy(self, *args: object) -> None:
        del args
        self.release_platform_resources()

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
        self._context.dispatcher.dispatch(window_close_requested(self._window_id))
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

    def _report_state(self) -> None:
        self._context.dispatcher.dispatch(
            window_state_changed(
                self._window_id,
                visible=self.isVisible(),
                minimized=self.isMinimized(),
                opacity=self._current_opacity,
                configured_opacity=self._configured_opacity,
                input_blocked=self.input_blocked,
            )
        )


def build_profile_window(
    config: WindowConfig,
    context: Context,
    *,
    attachments: WindowAttachments | None = None,
) -> RuntimeWindow:
    """Build a runtime window whose content is a profile node tree.

    ``attachments`` names the dwell settings and pointer locators this window
    installs; the attachment runtime provides them.
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
        layout.addWidget(context.engine.node_builder.build(config.content))
        for locator in installed.pointer_locators:
            install_pointer_locator(surface, locator)
        return surface

    return RuntimeWindow(
        window_id=config.id,
        title=config.title,
        overlay=config.overlay,
        chrome=config.chrome,
        opacity=config.opacity,
        minimum_size=config.minimum_size,
        build_content=build_content,
        context=context,
        dwell=installed.dwell,
        style=config.style,
    )
