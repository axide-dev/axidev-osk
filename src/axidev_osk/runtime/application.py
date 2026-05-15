"""Application runtime orchestration for Axidev OSK."""

from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from ..application.quit_controller import ApplicationQuitController
from ..components import register_components
from ..config.defaults import build_default_app_config
from ..config.models import AppConfig, ChromeConfig, PromptConfig, SurfaceConfig, WindowConfig
from ..services import register_services
from ..services.keyboard import KeyboardService
from ..styles.theme import apply_theme
from ..windows.surface import register_surfaces
from .context import Context
from .dispatcher import Dispatcher
from .event_handlers import register_context_command_handlers, register_event_handlers, route_hot_corner_triggered
from .events import WindowCloseRequested
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
    ) -> None:
        """Create the main runtime.

        Args:
            app: Existing QApplication.
            config: Optional declarative app config.
            services: Optional pre-populated service registry for tests.
            event_handlers: Optional pre-populated handler registry for tests.

        Returns:
            None.

        Side effects:
            Creates services, registries, dispatcher, and controllers.
        """

        self._app = app
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
            prompt=self._show_quit_prompt,
            parent=app,
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
        for service in self._services.services():
            service.start(self.context)
        for window_id in self._config.startup_window_ids:
            window = self._window_manager.show(window_id)
            self._quit_controller.register_window(window)
        for service in self._services.services():
            self._quit_controller.register_quit_callback(service.stop)
        self._quit_controller.install_signal_handlers()
        self._prompt_for_linux_permissions_if_needed()
        return self._app.exec()

    def _prompt_for_linux_permissions_if_needed(self) -> None:
        if self._keyboard.needs_permission_setup:
            QTimer.singleShot(0, self._show_linux_permission_prompt)

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

    def _handle_hot_corner_triggered(self, event: object) -> None:
        """Map hot-corner events to managed window visibility commands."""

        route_hot_corner_triggered(event, self)

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

    def _show_linux_permission_prompt(self) -> None:
        prompt_config = self._config.linux_permission_prompt
        parent = self._window_manager.get_or_create(self._config.keyboard_window_id)
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

        if waiter.result == "open_terminal":
            self._open_linux_permission_terminal()
        elif waiter.result == "setup_here":
            self._run_linux_permission_setup()
        elif waiter.result == "already_configured":
            QMessageBox.information(
                parent,
                "Log Out Required",
                (
                    "The Linux permission setup may already be applied, but this desktop session "
                    "does not have the updated group membership yet.\n\n"
                    "Log out and back in, then relaunch axidev-osk and test keyboard output again."
                ),
            )

    def _open_linux_permission_terminal(self) -> None:
        # Lazy import: this Linux-only helper drags in subprocess/terminal
        # detection logic that should not be loaded on macOS or Windows
        # where Linux permission prompts are never raised.
        from ..application.linux_permissions import launch_permission_script_in_terminal

        script_path = self._keyboard.permission_setup_script_path
        parent = self._window_manager.get_or_create(self._config.keyboard_window_id)
        if script_path is None:
            QMessageBox.warning(parent, "Permission Helper Missing", self._keyboard.permission_setup_text)
            return
        if launch_permission_script_in_terminal(script_path):
            QMessageBox.information(
                parent,
                "Terminal Opened",
                (
                    "A terminal window was opened for the Linux permission helper.\n\n"
                    "Complete the sudo prompt there. When the script finishes, log out and back in, "
                    "then relaunch axidev-osk and test keyboard output again."
                ),
            )
            return
        QMessageBox.warning(parent, "No Terminal Launcher Found", self._keyboard.permission_setup_text)

    def _run_linux_permission_setup(self) -> None:
        outcome = self._keyboard.setup_permissions()
        parent = self._window_manager.get_or_create(self._config.keyboard_window_id)
        status_label = parent.findChild(QWidget, "statusLabel")
        if status_label is not None and hasattr(status_label, "setText"):
            status_label.setText(self._keyboard.status_text)  # type: ignore[attr-defined]
        if outcome.error_text is not None:
            QMessageBox.warning(parent, "Permission Setup Failed", f"{outcome.error_text}\n\n{self._keyboard.permission_setup_text}")
            return
        if outcome.requires_logout:
            detail = (
                "Linux permission setup finished, but the new group membership is not active "
                "in this session yet.\n\n"
                "Log out and back in, then relaunch axidev-osk and test keyboard output again."
            )
            if outcome.helper_path is not None:
                detail = f"{detail}\n\nHelper script: {outcome.helper_path}"
            QMessageBox.information(parent, "Log Out Required", detail)
            return
        if self._keyboard.ready:
            detail = "Linux keyboard permissions are available now. Keyboard output is ready."
            if outcome.already_granted:
                detail = "Linux keyboard permissions were already available in this session. Keyboard output is ready."
            QMessageBox.information(parent, "Permission Ready", detail)
            return
        QMessageBox.information(parent, "Permission Setup", self._keyboard.permission_setup_text)
