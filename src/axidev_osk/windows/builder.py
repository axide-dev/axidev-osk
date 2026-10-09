"""Generic window builder for runtime window configs."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QCloseEvent, QHideEvent, QShowEvent
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from ..config.models import ChromeConfig, DwellClickConfig, OverlayConfig
from ..config.profile import StyleConfig, WindowConfig
from ..attachments.runtime import WindowAttachments
from ..components.pointer_locator import install_pointer_locator
from ..nodes import apply_style
from ..runtime.context import Context
from ..runtime.engine_messages import window_visibility_changed
from ..runtime.events import window_close_requested, window_drag_ended, window_drag_started
from .chrome import OverlayChromeWidgets, install_overlay_chrome
from .dwell_click import DwellClickController
from .opacity import WindowOpacityController
from .overlay import configure_always_on_top_window, configure_plain_window
from .surface import RootSurface


class RuntimeWindow(QMainWindow):
    """Generic host window around configured content.

    The class owns only Qt event interception and overlay show handling. Window
    identity, title, content, chrome, and overlay behavior all come from config.
    Close requests are routed through the runtime dispatcher via
    ``window.close_requested`` events; the quit controller subscribes to that
    event to drive shutdown rather than relying on a Qt signal side channel.
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
        parent: QWidget | None = None,
    ) -> None:
        """Create a generic runtime window around content built by ``build_content``.

        Side effects:
            Builds child widgets and configures platform overlay behavior.
        """

        super().__init__(parent)
        self._window_id = window_id
        self._context = context
        self._configured_opacity = opacity
        self._minimum_size = minimum_size
        self._quit_controller_managed = False
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
                            lambda: context.dispatcher.dispatch_event(window_drag_started(window_id))
                        )
                        if use_runtime_drag_motion
                        else None,
                        on_drag_ended=(
                            lambda: context.dispatcher.dispatch_event(window_drag_ended(window_id))
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

    def set_visual_opacity(self, opacity: float) -> None:
        """Set opacity through the platform-supported window implementation."""

        self._opacity.set_opacity(opacity)

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

    def set_quit_controller_managed(self, managed: bool) -> None:
        """Set whether close events should request managed app quit.

        Args:
            managed: ``True`` when the quit controller owns close behavior.

        Returns:
            None.

        Side effects:
            Changes future close-event handling.
        """

        self._quit_controller_managed = managed

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
        self.setMinimumSize(resolved_minimum_size)
        self.resize(resolved_minimum_size)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        """Route managed close requests through the runtime dispatcher."""

        removed_output = getattr(self._overlay, "has_removed_output", None)
        if removed_output is not None and removed_output():
            event.ignore()
            return
        if not self._quit_controller_managed:
            super().closeEvent(event)
            return
        self._context.dispatcher.dispatch_event(window_close_requested(self._window_id))
        event.ignore()

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        """Let the overlay controller apply show-time platform fixes."""

        super().showEvent(event)
        self.apply_startup_size(minimum_size=self._minimum_size)
        self._overlay.handle_show()
        if self._dwell_click is not None:
            self._dwell_click.start()
        self._report_visibility()

    def hideEvent(self, event: QHideEvent) -> None:  # type: ignore[override]
        """Stop dwell sampling while this window is hidden."""

        if self._dwell_click is not None:
            self._dwell_click.stop()
        super().hideEvent(event)
        self._report_visibility()

    def changeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        """Report minimize and restore as window observations."""

        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._report_visibility()

    def _report_visibility(self) -> None:
        self._context.dispatcher.dispatch_event(
            window_visibility_changed(self._window_id, self.isVisible(), self.isMinimized())
        )


def build_profile_window(
    config: WindowConfig,
    context: Context,
    *,
    attachments: WindowAttachments | None = None,
    parent: QWidget | None = None,
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
        parent=parent,
    )
