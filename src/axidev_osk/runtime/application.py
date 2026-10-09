"""Application runtime: run one profile on the engine.

The runtime owns process lifecycle, services, windows, and the queue. Every
decision about what appears and how controls behave comes from the active
profile.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from ..application.linux_permissions import open_permission_setup_terminal
from ..application.quit_controller import ApplicationQuitController
from ..attachments.runtime import AttachmentRuntime
from ..config.profile import ProfileConfig
from ..hot_corner.service import HotCornerService
from ..messages import MessageResult
from ..python_defaults.default_profile import build_default_config
from ..services import register_services
from ..services.keyboard import KeyboardService
from ..services.process import ProcessService
from ..styles.theme import apply_theme
from ..windows.builder import RuntimeWindow, build_profile_window
from .context import Context
from .dispatcher import Dispatcher
from .engine import build_engine
from .engine_messages import APP_QUIT_REQUESTED, app_quit_requested, linux_permission_setup_opened
from .event_handlers import register_event_handlers
from .events import (
    WINDOW_CLOSE_REQUESTED,
    WindowEventArguments,
    register_builtin_events,
    secure_input_panel_prepared,
    secure_input_panel_released,
)
from .qt_wake import QtDispatcherWake
from .registries import EventHandlerRegistry, ServiceRegistry
from .window_manager import WindowFactory, WindowManager

_logger = logging.getLogger(__name__)


class ApplicationRuntime:
    """Own QApplication-facing lifecycle, services, the queue, and profile windows."""

    def __init__(
        self,
        app: QApplication,
        *,
        root_config: Mapping[str, Any] | None = None,
        services: ServiceRegistry | None = None,
        event_handlers: EventHandlerRegistry | None = None,
        confirm_quit: bool = True,
        show_startup_windows: bool = True,
    ) -> None:
        """Create the runtime for one root config.

        Args:
            app: Existing QApplication.
            root_config: Root config map; the bundled default profile when omitted.
            services: Optional pre-populated service registry for tests.
            event_handlers: Optional pre-populated runtime handler registry for tests.
            confirm_quit: Whether quit requests ask the profile before shutting down.
            show_startup_windows: Whether to show ``show_on_start`` windows immediately.
        """

        self._app = app
        self._show_startup_windows = show_startup_windows
        self._active_pointer_drag_window_id: str | None = None
        self._pointer_drag_remainder = (0.0, 0.0)
        self._secure_input_panel_prepared = False
        self._dispatcher = Dispatcher()
        self._dispatcher_wake = QtDispatcherWake(self._dispatcher, parent=app)
        register_builtin_events(self._dispatcher)
        self._services = services or ServiceRegistry()
        if services is None:
            register_services(self._services, parent=app)
        self._keyboard = self._services.get("keyboard", KeyboardService)
        self._processes = ProcessService(parent=app)
        engine = build_engine(self._dispatcher, keyboard=self._keyboard, processes=self._processes)
        self.context = Context(dispatcher=self._dispatcher, keyboard=self._keyboard, engine=engine)
        self._profile: ProfileConfig = engine.decoder().decode_root(
            root_config if root_config is not None else build_default_config()
        ).profile
        self._window_manager = WindowManager()
        hot_corners = self._services.find("hot_corner")
        self._attachments = AttachmentRuntime(
            self._dispatcher,
            engine.profile,
            window_lookup=self._window_manager.get,
            hot_corners=hot_corners if isinstance(hot_corners, HotCornerService) else None,
        )
        self._quit_controller = ApplicationQuitController(
            app,
            ask_to_quit=self._ask_to_quit if confirm_quit else None,
            parent=app,
        )
        self._window_manager.set_factories(
            {window.id: self._window_factory(window.id) for window in self._profile.windows}
        )
        handlers = event_handlers or EventHandlerRegistry()
        if event_handlers is None:
            register_event_handlers(handlers)
        handlers.install(self._dispatcher, self)
        if WINDOW_CLOSE_REQUESTED not in self._profile.on:
            self._dispatcher.add_event_handler(WINDOW_CLOSE_REQUESTED, self._default_close_requested)

    @property
    def profile(self) -> ProfileConfig:
        return self._profile

    def start(self) -> int:
        """Start the profile, services, and startup windows, then run the Qt event loop."""

        apply_theme(self._app, qss=self._profile.theme.qss)
        self.context.engine.profile.start(self._profile)
        self._attachments.start(self._profile)
        self._processes.start(self.context)
        self._quit_controller.register_quit_callback(self._processes.stop)
        for service in self._services.autostart_services():
            service.start(self.context)
        if self._show_startup_windows:
            for window in self._profile.windows:
                if window.show_on_start:
                    self._window_manager.show(window.id)
        for service in self._services.services():
            self._quit_controller.register_quit_callback(service.stop)
        self._quit_controller.install_signal_handlers()
        if self._keyboard in self._services.autostart_services():
            QTimer.singleShot(0, self._keyboard.publish_status)
        return self._app.exec()

    def _window_factory(self, window_id: str) -> WindowFactory:
        window_config = self._profile.window(window_id)

        def build(parent: QWidget | None) -> RuntimeWindow:
            window = build_profile_window(
                window_config,
                self.context,
                attachments=self._attachments.for_window(window_id),
                parent=parent,
            )
            self._quit_controller.register_window(window)
            return window

        return build

    def _ask_to_quit(self) -> None:
        """Let the profile confirm a quit, or quit when it has no opinion."""

        if APP_QUIT_REQUESTED in self._profile.on:
            self._dispatcher.dispatch_event(app_quit_requested("request"))
        else:
            self._quit_controller.shutdown()

    def _default_close_requested(self, event: WindowEventArguments) -> MessageResult:
        del event
        self._quit_controller.request_quit()
        return []

    def _quit(self, exit_code: int) -> MessageResult:
        self._quit_controller.shutdown(exit_code)
        return []

    def _open_permission_setup(self) -> MessageResult:
        return [linux_permission_setup_opened(open_permission_setup_terminal())]

    def _prepare_secure_input_panel(self) -> MessageResult:
        """Start keyboard output and show the profile's lock-screen window."""

        if self._secure_input_panel_prepared:
            return [secure_input_panel_prepared()]
        window_id = self._attachments.secure_input_panel_window
        if window_id is None:
            raise RuntimeError("The active profile has no secure_input_panel attachment")
        try:
            self._keyboard.start(self.context)
            self._keyboard.publish_status()
            window = self._window_manager.show(window_id)
            window.set_close_enabled(False)
        except Exception:
            try:
                self._window_manager.destroy(window_id)
            except Exception:
                _logger.exception("Failed to destroy a partially prepared secure input panel")
            try:
                self._keyboard.shutdown()
            except Exception:
                _logger.exception("Failed to shut down keyboard output after panel preparation failed")
            raise
        self._secure_input_panel_prepared = True
        return [secure_input_panel_prepared()]

    def _release_secure_input_panel(self) -> MessageResult:
        """Destroy the panel while retaining this KWin input-method connection."""

        if not self._secure_input_panel_prepared:
            return [secure_input_panel_released()]
        window_id = self._attachments.secure_input_panel_window
        try:
            self._keyboard.reset_state()
        finally:
            try:
                if window_id is not None:
                    self._window_manager.destroy(window_id)
            finally:
                self._secure_input_panel_prepared = False
        return [secure_input_panel_released()]

    def _commit_window_surface(self, window: QWidget) -> None:
        """Commit a moved layer-shell surface through interested services."""

        surface = int(window.winId())
        for service in self._services.services():
            commit_surface = getattr(service, "commit_surface", None)
            if commit_surface is not None:
                commit_surface(surface)

    def _set_pointer_drag_active(self, enabled: bool) -> None:
        """Start or stop relative-pointer collection in interested services."""

        for service in self._services.services():
            if enabled:
                begin_drag = getattr(service, "begin_drag", None)
                if begin_drag is not None:
                    begin_drag()
            else:
                end_drag = getattr(service, "end_drag", None)
                if end_drag is not None:
                    end_drag()

