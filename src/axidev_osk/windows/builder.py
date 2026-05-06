"""Generic window builder for runtime window configs."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from ..config.models import WindowConfig
from ..runtime.context import Context
from ..runtime.events import WindowCloseRequested
from .chrome import install_overlay_chrome
from .overlay import configure_always_on_top_window, configure_plain_window


class RuntimeWindow(QMainWindow):
    """Generic host window built entirely from ``WindowConfig``.

    The class owns only Qt event interception and overlay show handling. Window
    identity, title, content, chrome, and overlay behavior all come from config.
    Close requests are routed through the runtime dispatcher via
    ``WindowCloseRequested`` events; the quit controller subscribes to that
    event to drive shutdown rather than relying on a Qt signal side channel.
    """

    def __init__(self, config: WindowConfig, context: Context, parent: QWidget | None = None) -> None:
        """Create a generic runtime window.

        Args:
            config: Declarative window config.
            context: Runtime context used to build content and dispatch events.
            parent: Optional Qt parent.

        Returns:
            None.

        Side effects:
            Builds child widgets and configures platform overlay behavior.
        """

        super().__init__(parent)
        self._config = config
        self._context = context
        self._quit_controller_managed = False
        self.setProperty("componentType", "window")
        self.setProperty("componentId", config.id)
        self.setWindowTitle(config.title)
        if config.overlay.always_on_top:
            self._overlay = configure_always_on_top_window(self, config=config.overlay.config)
        else:
            self._overlay = configure_plain_window(self)

        central = context.surfaces.build(config.surface, context)
        if config.chrome.enabled and getattr(self._overlay, "uses_custom_chrome", False):
            central_layout = central.layout()
            if isinstance(central_layout, QVBoxLayout):
                install_overlay_chrome(
                    central_layout,
                    title=self.windowTitle(),
                    parent=central,
                    on_move=self._overlay.move_by,
                    on_resize=self._overlay.resize_by,
                )
        self.setCentralWidget(central)
        self.apply_startup_size(minimum_size=config.surface.minimum_size)

    @property
    def window_id(self) -> str:
        """Return this window's deterministic runtime ID."""

        return self._config.id

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

        if not self._quit_controller_managed:
            super().closeEvent(event)
            return
        self._context.dispatcher.dispatch_event(WindowCloseRequested(window_id=self._config.id))
        event.ignore()

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        """Let the overlay controller apply show-time platform fixes."""

        super().showEvent(event)
        self.apply_startup_size(minimum_size=self._config.surface.minimum_size)
        self._overlay.handle_show()


def build_window(config: WindowConfig, context: Context, *, parent: QWidget | None = None) -> RuntimeWindow:
    """Build a generic runtime window from config.

    Args:
        config: Declarative window config.
        context: Runtime context.
        parent: Optional Qt parent.

    Returns:
        A generic Qt window hosting configured content.

    Side effects:
        Constructs widgets and configures the selected overlay backend.
    """

    return RuntimeWindow(config, context, parent=parent)
