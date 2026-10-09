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
from PySide6.QtWidgets import QApplication

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
from .app_messages import (
    APP_QUIT,
    APP_QUIT_REQUESTED,
    LINUX_OPEN_PERMISSION_SETUP,
    SECURE_INPUT_PANEL_PREPARE,
    SECURE_INPUT_PANEL_RELEASE,
    WINDOW_CLOSE_REQUESTED,
    AppQuitArguments,
    WindowArguments,
    app_quit_requested,
    decode_app_quit,
    linux_permission_setup_opened,
    secure_input_panel_prepared,
    secure_input_panel_released,
    window_close,
    window_show,
)
from .context import Context
from .decoding import EmptyArguments, decode_empty
from .dispatcher import Dispatcher
from .engine import build_engine
from .event_handlers import PointerDragRouter, register_display_recovery, register_window_actions
from .qt_wake import QtDispatcherWake
from .registries import ServiceRegistry
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
        confirm_quit: bool = True,
        show_startup_windows: bool = True,
    ) -> None:
        """Create the runtime for one root config.

        Args:
            app: Existing QApplication.
            root_config: Root config map; the bundled default profile when omitted.
            services: Optional pre-populated service registry for tests.
            confirm_quit: Whether quit requests may ask the profile before shutting down.
            show_startup_windows: Whether to show ``show_on_start`` windows immediately.
        """

        self._app = app
        self._show_startup_windows = show_startup_windows
        self._dispatcher = Dispatcher()
        self._dispatcher_wake = QtDispatcherWake(self._dispatcher, parent=app)
        self._services = services or ServiceRegistry()
        if services is None:
            register_services(self._services, parent=app)
        self._keyboard = self._services.get("keyboard", KeyboardService)
        processes = ProcessService(parent=app)
        self._services.register("processes", processes)
        engine = build_engine(self._dispatcher, keyboard=self._keyboard, processes=processes)
        self.context = Context(dispatcher=self._dispatcher, keyboard=self._keyboard, engine=engine)
        self._profile: ProfileConfig = engine.decoder().decode_root(
            root_config if root_config is not None else build_default_config()
        )
        hot_corners = self._services.find("hot_corner")
        self._attachments = AttachmentRuntime(
            self._dispatcher,
            engine.profile,
            window_lookup=lambda window_id: self._window_manager.get(window_id),
            hot_corners=hot_corners if isinstance(hot_corners, HotCornerService) else None,
        )
        self._window_manager = WindowManager(
            {window.id: self._window_factory(window.id) for window in self._profile.windows}
        )
        # One decision: ask the profile only when quits may be confirmed and the profile handles the request.
        asks = confirm_quit and APP_QUIT_REQUESTED in self._profile.on
        self._quit_controller = ApplicationQuitController(
            app,
            ask_to_quit=self._ask_to_quit if asks else None,
            parent=app,
        )
        register_window_actions(self._dispatcher, self._window_manager)
        register_display_recovery(self._dispatcher, self._window_manager, self._services)
        self._pointer_drag = PointerDragRouter(self._window_manager, self._services)
        self._pointer_drag.register(self._dispatcher)
        self._dispatcher.register_action(APP_QUIT, decode_app_quit, self._quit)
        self._dispatcher.register_action(SECURE_INPUT_PANEL_PREPARE, decode_empty, self._prepare_secure_input_panel)
        self._dispatcher.register_action(SECURE_INPUT_PANEL_RELEASE, decode_empty, self._release_secure_input_panel)
        self._dispatcher.register_action(LINUX_OPEN_PERMISSION_SETUP, decode_empty, self._open_permission_setup)
        self._dispatcher.add_event_handler(WINDOW_CLOSE_REQUESTED, self._default_close)

    @property
    def profile(self) -> ProfileConfig:
        return self._profile

    def start(self) -> int:
        """Start the profile, services, and startup windows, then run the Qt event loop.

        Startup windows are shown through the queue, so every window is built
        inside a queue drain like the windows profiles show later. Shutdown
        stops the profile first, so its callbacks never see teardown.
        """

        apply_theme(self._app, self._profile.theme)
        self.context.engine.profile.start(self._profile)
        self._attachments.start(self._profile)
        for service in self._services.autostart_services():
            service.start(self.context)
        if self._show_startup_windows:
            self._dispatcher.dispatch(
                *(window_show(window.id) for window in self._profile.windows if window.show_on_start)
            )
        self._quit_controller.register_quit_callback(self.context.engine.profile.stop)
        for service in self._services.services():
            self._quit_controller.register_quit_callback(service.stop)
        self._quit_controller.register_quit_callback(self._window_manager.close_all)
        self._quit_controller.install_signal_handlers()
        if self._keyboard in self._services.autostart_services():
            QTimer.singleShot(0, self._keyboard.publish_status)
        return self._app.exec()

    def _window_factory(self, window_id: str) -> WindowFactory:
        window_config = self._profile.window(window_id)

        def build() -> RuntimeWindow:
            return build_profile_window(window_config, self.context, attachments=self._attachments.for_window(window_id))

        return build

    def _ask_to_quit(self, reason: str) -> None:
        self._dispatcher.dispatch(app_quit_requested(reason))

    def _default_close(self, event: WindowArguments) -> MessageResult:
        """Apply Qt's close rule unless the window turned it off with ``default_close``.

        Closing the window closes it; closing the last visible window asks to
        quit instead. Profile handlers for ``window.close_requested`` run too.
        """

        if not self._profile.window(event.window_id).default_close:
            return []
        others_visible = any(
            window.isVisible() for window in self._window_manager.all_windows() if window.window_id != event.window_id
        )
        if others_visible:
            return [window_close(event.window_id)]
        self._quit_controller.request_quit("window_closed")
        return []

    def _quit(self, arguments: AppQuitArguments) -> MessageResult:
        self._quit_controller.shutdown(arguments.exit_code)
        return []

    def _open_permission_setup(self, arguments: EmptyArguments) -> MessageResult:
        del arguments
        return [linux_permission_setup_opened(open_permission_setup_terminal())]

    def _secure_input_panel_window(self) -> str:
        window_id = self._attachments.secure_input_panel_window
        if window_id is None:
            raise RuntimeError("The active profile has no secure_input_panel attachment")
        return window_id

    def _prepare_secure_input_panel(self, arguments: EmptyArguments) -> MessageResult:
        """Start keyboard output and show the profile's lock-screen window.

        The panel counts as prepared while its window is live and visible.
        Keyboard output that cannot start fails the preparation, so the
        supervisor hears ``ERROR`` instead of a panel that cannot type.
        """

        del arguments
        window_id = self._secure_input_panel_window()
        existing = self._window_manager.get(window_id)
        if existing is not None and existing.isVisible():
            return [secure_input_panel_prepared()]
        try:
            self._keyboard.start(self.context)
            if not self._keyboard.ready:
                raise RuntimeError(f"Keyboard output is unavailable: {self._keyboard.status_text}")
            self._keyboard.publish_status()
            window = self._window_manager.show(window_id)
            window.set_close_enabled(False)
        except Exception:
            try:
                self._window_manager.close(window_id)
            except Exception:
                _logger.exception("Failed to close a partially prepared secure input panel")
            try:
                self._keyboard.shutdown()
            except Exception:
                _logger.exception("Failed to shut down keyboard output after panel preparation failed")
            raise
        return [secure_input_panel_prepared()]

    def _release_secure_input_panel(self, arguments: EmptyArguments) -> MessageResult:
        """Close the panel while retaining this KWin input-method connection."""

        del arguments
        window_id = self._secure_input_panel_window()
        if self._window_manager.get(window_id) is None:
            return [secure_input_panel_released()]
        try:
            self._keyboard.reset_state()
        finally:
            self._window_manager.close(window_id)
        return [secure_input_panel_released()]
