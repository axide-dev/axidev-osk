"""Application runtime orchestration for Axidev OSK."""

from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QWidget

from ..messages import MessageResult
from ..application.linux_permissions import LinuxPermissionController
from ..application.quit_controller import ApplicationQuitController
from ..components import register_components
from ..config.defaults import build_default_app_config
from ..config.models import AppConfig, ChromeConfig, PromptConfig, SurfaceConfig, WindowConfig
from ..services import register_services
from ..services.keyboard import KeyboardService
from ..styles.theme import apply_theme
from ..windows.surface import register_surfaces
from .context import Context
from .behaviors import BehaviorRegistry, register_builtin_behaviors
from .dispatcher import Dispatcher
from .event_handlers import (
    register_context_action_handlers,
    register_event_handlers,
    route_hot_corner_triggered,
)
from .events import (
    HotCornerTriggeredArguments,
    WindowCloseRequestedArguments,
    register_builtin_events,
    secure_input_panel_prepared,
    secure_input_panel_released,
)
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
        self._active_pointer_drag_window_id: str | None = None
        self._pointer_drag_remainder = (0.0, 0.0)
        self._secure_input_panel_prepared = False
        self._config = config or build_default_app_config()
        self._dispatcher = Dispatcher()
        register_builtin_events(self._dispatcher)
        self._services = services or ServiceRegistry()
        if services is None:
            register_services(self._services, parent=app)
        self._keyboard = self._services.get("keyboard", KeyboardService)
        self._state = StateStore()
        self._components = ComponentRegistry()
        self._surfaces = SurfaceRegistry()
        self._behaviors = BehaviorRegistry()
        register_builtin_behaviors(self._behaviors)
        self._behaviors.load(self._config)
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
            behaviors=self._behaviors,
        )
        context_handlers = EventHandlerRegistry()
        register_context_action_handlers(context_handlers)
        context_handlers.install(self._dispatcher, self.context)
        self._behaviors.bind_context(self.context)
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
        autostart_services = tuple(self._services.autostart_services())
        for service in autostart_services:
            service.start(self.context)
        if any(service is self._keyboard for service in autostart_services):
            self._behaviors.activate()
        if self._show_startup_windows:
            for window_id in self._config.startup_window_ids:
                window = self._window_manager.show(window_id)
                self._quit_controller.register_window(window)
        for service in self._services.services():
            self._quit_controller.register_quit_callback(service.stop)
        self._quit_controller.install_signal_handlers()
        self._linux_permissions.prompt_if_needed()
        return self._app.exec()

    def _handle_window_close_requested(self, event: WindowCloseRequestedArguments) -> MessageResult:
        """Route close-request events to the quit controller.

        Args:
            event: Any runtime event; non-matching events are ignored.

        Returns:
            None.

        Side effects:
            Triggers ``ApplicationQuitController.request_quit`` when the
            event is a ``WindowCloseRequested``.
        """

        del event
        self._quit_controller.request_quit()
        return []

    def _handle_hot_corner_triggered(self, event: HotCornerTriggeredArguments) -> MessageResult:
        """Map hot-corner events to managed window visibility actions."""

        return route_hot_corner_triggered(event, self)

    def _prepare_secure_input_panel(self) -> MessageResult:
        """Create the keyboard window and backend requested by the lock-screen button."""

        if self._secure_input_panel_prepared:
            return [secure_input_panel_prepared()]
        window_id = self._config.keyboard_window_id
        try:
            self._keyboard.start(self.context)
            self._behaviors.activate()
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
        try:
            self._keyboard.reset_state()
        finally:
            try:
                self._window_manager.destroy(self._config.keyboard_window_id)
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
