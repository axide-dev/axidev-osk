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
from ..hot_corner import HotCornerWindowToggleController
from ..styles.theme import apply_theme
from ..windows.surface import register_surfaces
from .commands import AppQuit, WindowClose, WindowHide, WindowShow
from .context import Context
from .dispatcher import Dispatcher
from .events import HotCornerTriggered, PromptResolved, WindowCloseRequested
from .registries import ComponentRegistry, SurfaceRegistry
from .state_store import StateStore
from .window_manager import WindowManager
from ..services.keyboard import KeyboardService

_logger = logging.getLogger(__name__)


class ApplicationRuntime:
    """Owns QApplication-facing lifecycle, services, state, and windows."""

    def __init__(self, app: QApplication, *, config: AppConfig | None = None) -> None:
        """Create the main runtime.

        Args:
            app: Existing QApplication.
            config: Optional declarative app config.

        Returns:
            None.

        Side effects:
            Creates services, registries, dispatcher, and controllers.
        """

        self._app = app
        self._config = config or build_default_app_config()
        self._dispatcher = Dispatcher()
        self._keyboard = KeyboardService()
        self._state = StateStore()
        self._components = ComponentRegistry()
        self._surfaces = SurfaceRegistry()
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
        self._keyboard.bind_context(self.context)
        self._window_manager = WindowManager(self.context)
        self._dispatcher.add_command_handler(WindowShow, lambda command: self._window_manager.show(command.window_id))
        self._dispatcher.add_command_handler(WindowHide, lambda command: self._window_manager.hide(command.window_id))
        self._dispatcher.add_command_handler(WindowClose, lambda command: self._window_manager.close(command.window_id))
        self._dispatcher.add_command_handler(AppQuit, lambda command: self._app.exit(command.exit_code))
        self._hot_corner = HotCornerWindowToggleController(
            self._dispatcher,
            config=self._config.hot_corner,
            parent=app,
        )
        self._quit_controller = ApplicationQuitController(
            app,
            prompt=self._show_quit_prompt,
            parent=app,
        )
        self._dispatcher.add_event_handler(self._handle_window_close_requested)
        self._dispatcher.add_event_handler(self._handle_hot_corner_triggered)

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
        self._keyboard.initialize()
        for window_id in self._config.startup_window_ids:
            window = self._window_manager.show(window_id)
            self._quit_controller.register_window(window)
        self._quit_controller.register_quit_callback(self._hot_corner.stop)
        self._quit_controller.register_quit_callback(self._keyboard.shutdown)
        self._quit_controller.install_signal_handlers()
        self._hot_corner.start()
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

        if not isinstance(event, HotCornerTriggered):
            return
        for window_id in self._config.hot_corner.bindings.get(event.corner, []):
            if self._window_manager.is_visible(window_id):
                self._dispatcher.dispatch_command(WindowHide(window_id))
            else:
                self._dispatcher.dispatch_command(WindowShow(window_id))

    def _show_quit_prompt(self, parent: QWidget | None) -> bool:
        prompt_config = self._config.quit_prompt
        prompt_window = self._window_manager.create_transient(
            self._build_prompt_window_config(prompt_config),
            parent=parent,
        )
        event_loop = QEventLoop(prompt_window)
        result = {"accepted": False}
        unsubscribe = None

        def handle_prompt(event: object) -> None:
            if not isinstance(event, PromptResolved):
                return
            if event.prompt_id != prompt_config.id:
                return
            result["accepted"] = event.result == "accepted"
            if event_loop.isRunning():
                event_loop.quit()

        unsubscribe = self._dispatcher.add_event_handler(handle_prompt)
        prompt_window.show()
        event_loop.exec()
        if unsubscribe is not None:
            unsubscribe()
        prompt_window.close()
        return result["accepted"]

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
        result = {"role": "rejected"}
        unsubscribe = None

        def handle_prompt(event: object) -> None:
            if not isinstance(event, PromptResolved):
                return
            if event.prompt_id != prompt_config.id:
                return
            result["role"] = event.result
            if event_loop.isRunning():
                event_loop.quit()

        unsubscribe = self._dispatcher.add_event_handler(handle_prompt)
        prompt_window.show()
        event_loop.exec()
        if unsubscribe is not None:
            unsubscribe()
        prompt_window.close()

        if result["role"] == "open_terminal":
            self._open_linux_permission_terminal()
        elif result["role"] == "setup_here":
            self._run_linux_permission_setup()
        elif result["role"] == "already_configured":
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
