"""Application runtime orchestration for Axidev OSK."""

from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QWidget

from ..application.linux_permissions import LinuxPermissionController
from ..application.quit_controller import ApplicationQuitController
from ..components import register_components
from ..config.defaults import build_default_app_config
from ..config.models import AppConfig, ChromeConfig, PromptConfig, SurfaceConfig, WindowConfig
from ..services import register_services
from ..services.keyboard import KeyboardService
from ..services.kwin_lock import KWinLockService
from ..styles.theme import apply_theme
from ..windows.surface import register_surfaces
from .context import Context
from .dispatcher import Dispatcher
from .event_handlers import (
    register_context_command_handlers,
    register_event_handlers,
    route_component_pressed,
    route_hot_corner_triggered,
)
from .events import ScreenLockStateChanged, WindowCloseRequested
from .prompt import PromptResolutionWaiter
from .registries import ComponentRegistry, EventHandlerRegistry, ServiceRegistry, SurfaceRegistry
from .state_store import StateStore
from .window_manager import WindowManager

_logger = logging.getLogger(__name__)


class ApplicationRuntime:
    """Owns QApplication-facing lifecycle, services, state, and windows."""

    def __init__(
        self,
        app: QApplication,
        *,
        config: AppConfig | None = None,
        services: ServiceRegistry | None = None,
        event_handlers: EventHandlerRegistry | None = None,
        confirm_quit: bool = True,
        show_startup_windows: bool = True,
    ) -> None:
        """Create the main runtime.

        Args:
            app: Existing QApplication.
            config: Optional declarative app config.
            services: Optional pre-populated service registry for tests.
            event_handlers: Optional pre-populated handler registry for tests.
            confirm_quit: Whether shutdown requests require confirmation.
            show_startup_windows: Whether to create configured startup windows immediately.

        Returns:
            None.

        Side effects:
            Creates services, registries, dispatcher, and controllers.
        """

        self._app = app
        self._show_startup_windows = show_startup_windows
        self._screen_locked: bool | None = None
        self._config = config or build_default_app_config()
        self._dispatcher = Dispatcher()
        self._services = services or ServiceRegistry()
        if services is None:
            register_services(self._services, parent=app)
        self._keyboard = self._services.get("keyboard", KeyboardService)
        self._state = StateStore()
        self._components = ComponentRegistry()
        self._surfaces = SurfaceRegistry()
        self._event_handlers = event_handlers or EventHandlerRegistry()
        if event_handlers is None:
            register_event_handlers(self._event_handlers)
        register_components(self._components)
        register_surfaces(self._surfaces)
        self.context = Context(
            config=self._config,
            dispatcher=self._dispatcher,
            keyboard=self._keyboard,
            state=self._state,
            components=self._components,
            surfaces=self._surfaces,
        )
        self._dispatcher.bind_context(self.context)
        context_handlers = EventHandlerRegistry()
        register_context_command_handlers(context_handlers)
        context_handlers.install(self._dispatcher, self.context)
        self._window_manager = WindowManager(self.context)
        self._event_handlers.install(self._dispatcher, self)
        self._quit_controller = ApplicationQuitController(
            app,
            prompt=self._show_quit_prompt if confirm_quit else lambda _parent: True,
            parent=app,
        )
        self._linux_permissions = LinuxPermissionController(
            config=self._config,
            dispatcher=self._dispatcher,
            keyboard=self._keyboard,
            window_manager=self._window_manager,
            build_prompt_window_config=self._build_prompt_window_config,
        )

    def start(self) -> int:
        """Start services, windows, hot corner, and the Qt event loop.

        Args:
            None.

        Returns:
            QApplication exit code.

        Side effects:
            Initializes keyboard output and shows startup windows.
        """

        apply_theme(self._app)
        for service in self._services.autostart_services():
            service.start(self.context)
        if self._show_startup_windows:
            for window_id in self._config.startup_window_ids:
                window = self._window_manager.show(window_id)
                self._quit_controller.register_window(window)
        for service in self._services.services():
            self._quit_controller.register_quit_callback(service.stop)
        self._quit_controller.install_signal_handlers()
        self._linux_permissions.prompt_if_needed()
        return self._app.exec()

    def _handle_window_close_requested(self, event: object) -> None:
        """Route ``WindowCloseRequested`` events to the quit controller.

        Args:
            event: Any runtime event; non-matching events are ignored.

        Returns:
            None.

        Side effects:
            Triggers ``ApplicationQuitController.request_quit`` when the
            event is a ``WindowCloseRequested``.
        """

        if isinstance(event, WindowCloseRequested):
            self._quit_controller.request_quit()

    def _handle_screen_lock_state_changed(self, event: object) -> None:
        """Create or destroy secure runtime resources as KDE locks and unlocks."""

        if not isinstance(event, ScreenLockStateChanged):
            return
        if event.locked == self._screen_locked:
            if event.locked:
                self._services.get("kwin_lock", KWinLockService).activate()
            return
        window_id = self._config.keyboard_window_id
        if event.locked:
            try:
                self._keyboard.start(self.context)
                window = self._window_manager.show(window_id)
                window.set_close_enabled(False)
                self._services.get("kwin_lock", KWinLockService).activate()
            except Exception:
                try:
                    self._window_manager.destroy(window_id)
                except Exception:
                    _logger.exception("Failed to destroy a partially started lock window")
                try:
                    self._keyboard.shutdown()
                except Exception:
                    _logger.exception("Failed to shut down keyboard output after lock startup failed")
                raise
        else:
            try:
                self._window_manager.destroy(window_id)
            finally:
                self._keyboard.shutdown()
        self._screen_locked = event.locked

    def _handle_hot_corner_triggered(self, event: object) -> None:
        """Map hot-corner events to managed window visibility commands."""

        route_hot_corner_triggered(event, self)

    def _handle_component_pressed(self, event: object) -> None:
        """Map configured component actions to runtime commands."""

        route_component_pressed(event, self)

    def _show_quit_prompt(self, parent: QWidget | None) -> bool:
        prompt_config = self._config.quit_prompt
        prompt_window = self._window_manager.create_transient(
            self._build_prompt_window_config(prompt_config),
            parent=parent,
        )
        event_loop = QEventLoop(prompt_window)
        waiter = PromptResolutionWaiter(self._dispatcher, prompt_config.id, event_loop, default="rejected")
        waiter.start()
        prompt_window.show()
        event_loop.exec()
        waiter.stop()
        prompt_window.close()
        return waiter.result == "accepted"

    def _build_prompt_window_config(self, prompt: PromptConfig) -> WindowConfig:
        keyboard_window = next(
            window for window in self._config.windows if window.id == self._config.keyboard_window_id
        )
        return WindowConfig(
            id=prompt.window_id,
            title=prompt.title,
            surface=SurfaceConfig(
                id=prompt.surface_id,
                components=(prompt,),
                margins=prompt.margins,
                spacing=prompt.spacing,
                minimum_size=prompt.minimum_size,
            ),
            overlay=replace(keyboard_window.overlay, config=keyboard_window.overlay.config),
            chrome=ChromeConfig(enabled=False),
        )
