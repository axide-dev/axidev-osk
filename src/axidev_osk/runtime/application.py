"""Application runtime: run the profiles of one root config on the engine.

The runtime owns process lifecycle, services, windows, and the queue. Every
decision about what appears and how controls behave comes from the running
profile, which ``profile.switch`` replaces with another profile of the same
root config.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication

from ..application.linux_permissions import open_permission_setup_terminal
from ..application.quit_controller import ApplicationQuitController
from ..attachments.runtime import AttachmentRuntime
from ..config.profile import ProfileConfig, RootConfig
from ..hot_corner.service import HotCornerService
from ..messages import MessageResult
from ..services import register_services
from ..services.keyboard import KeyboardService
from ..services.process import ProcessService
from ..styles.theme import apply_theme
from ..windows.builder import RuntimeWindow, build_profile_window
from .app_messages import (
    APP_QUIT,
    APP_QUIT_REQUESTED,
    LINUX_OPEN_PERMISSION_SETUP,
    PROFILE_START,
    PROFILE_SWITCH,
    SECURE_INPUT_PANEL_PREPARE,
    SECURE_INPUT_PANEL_RELEASE,
    WINDOW_CLOSE_REQUESTED,
    AppQuitArguments,
    ProfileSwitchArguments,
    WindowCloseRequestedArguments,
    app_quit,
    app_quit_requested,
    decode_app_quit,
    decode_profile_switch,
    linux_permission_setup_opened,
    profile_start,
    secure_input_panel_prepared,
    secure_input_panel_released,
    window_close,
)
from .decoding import EmptyArguments, decode_empty
from .dispatcher import Dispatcher, Unsubscribe
from .engine import build_engine
from .event_handlers import PointerDragRouter, RelativePointer, register_display_recovery, register_window_actions
from .qt_wake import QtDispatcherWake
from .registries import ServiceRegistry
from .window_manager import WindowFactory, WindowManager

_logger = logging.getLogger(__name__)


class ProfileRollbackFailed(RuntimeError):
    """The previous profile could not start again after a switch failed, so no profile runs."""

    def __init__(self, previous: str, target: str, error: Exception) -> None:
        super().__init__(
            f"Profile {previous!r} could not start again after switching to {target!r} failed: "
            f"{type(error).__name__}: {error}"
        )


class ApplicationRuntime:
    """Own QApplication-facing lifecycle, services, the queue, and the running profile's windows."""

    def __init__(
        self,
        app: QApplication,
        *,
        root_config: Mapping[str, Any],
        services: ServiceRegistry | None = None,
        confirm_quit: bool = True,
        show_startup_windows: bool = True,
    ) -> None:
        """Create the runtime for one root config.

        Args:
            app: Existing QApplication.
            root_config: Root config map whose active profile runs.
            services: Optional pre-populated service registry for tests.
            confirm_quit: Whether quit requests may ask the profile before shutting down.
            show_startup_windows: Whether to show ``show_on_start`` windows immediately.
        """

        self._app = app
        # Every theme applies on top of the app's own look, so one theme never inherits another's.
        self._base_palette = QPalette(app.palette())
        self._base_font = QFont(app.font())
        self._show_startup_windows = show_startup_windows
        self._panel_prepared = False
        self._dispatcher = Dispatcher()
        self._dispatcher_wake = QtDispatcherWake(self._dispatcher, parent=app)
        self._services = services or ServiceRegistry()
        if services is None:
            register_services(self._services, parent=app)
        self._keyboard = self._services.get("keyboard", KeyboardService)
        processes = ProcessService(parent=app)
        self._services.register("processes", processes)
        engine = build_engine(self._dispatcher, keyboard=self._keyboard, processes=processes)
        self.engine = engine
        hot_corners = self._services.find("hot_corner")
        self._attachments = AttachmentRuntime(
            engine.bindings,
            engine.attachments,
            window_lookup=lambda window_id: self._window_manager.get(window_id),
            hot_corners=hot_corners if isinstance(hot_corners, HotCornerService) else None,
        )
        self._root: RootConfig = engine.decoder().decode_config(root_config)
        self._profile: ProfileConfig = self._root.active
        self._unbind_theme: Unsubscribe | None = None
        self._switching_to: str | None = None
        self._window_manager = WindowManager({})
        self._quit_controller = ApplicationQuitController(
            app,
            send_quit=lambda: self._dispatcher.dispatch(app_quit()),
            ask_to_quit=self._ask_to_quit if confirm_quit else None,
            parent=app,
        )
        relative_pointer = cast("RelativePointer | None", self._services.find("wayland_relative_pointer"))
        register_window_actions(self._dispatcher, self._window_manager, relative_pointer)
        register_display_recovery(self._dispatcher, self._window_manager)
        self._pointer_drag = PointerDragRouter(self._window_manager, relative_pointer)
        self._pointer_drag.register(self._dispatcher)
        self._dispatcher.register_action(APP_QUIT, decode_app_quit, self._quit, when_idle=True)
        self._dispatcher.register_action(PROFILE_SWITCH, decode_profile_switch, self._switch_profile, when_idle=True)
        self._dispatcher.register_action(PROFILE_START, decode_empty, self._start_switched_profile, when_idle=True)
        self._dispatcher.register_action(SECURE_INPUT_PANEL_PREPARE, decode_empty, self._prepare_secure_input_panel)
        self._dispatcher.register_action(SECURE_INPUT_PANEL_RELEASE, decode_empty, self._release_secure_input_panel)
        self._dispatcher.register_action(LINUX_OPEN_PERMISSION_SETUP, decode_empty, self._open_permission_setup)
        self._dispatcher.add_event_handler(WINDOW_CLOSE_REQUESTED, self._default_close)

    @property
    def profile(self) -> ProfileConfig:
        return self._profile

    def start(self) -> int:
        """Start the profile, services, and startup windows, then run the Qt event loop.

        Startup and a profile switch show start windows the same way. At
        startup that runs outside a queue drain, which is safe because
        building a window never drains: a binding that fails while it is
        bound posts its report. Shutdown closes the queue, then stops the
        profile, so its callbacks never see teardown. The shutdown steps are registered first: when a step of
        starting fails, they run before the error is raised.
        """

        self._quit_controller.register_quit_callback(self._dispatcher.close)
        self._quit_controller.register_quit_callback(self.engine.profile.stop)
        for service in self._services.services():
            self._quit_controller.register_quit_callback(service.stop)
        self._quit_controller.register_quit_callback(self._window_manager.close_all)
        try:
            self._dispatcher.dispatch(
                *self.engine.profile.set_observed(("app", "profiles"), list(self._root.profiles))
            )
            self._activate(self._profile)
            for service in self._services.autostart_services():
                service.start(self._dispatcher)
            self._show_start_windows()
        except BaseException:
            self._quit_controller.shutdown(1)
            raise
        self._quit_controller.install_signal_handlers()
        if self._keyboard in self._services.autostart_services():
            QTimer.singleShot(0, self._keyboard.publish_status)
        return self._app.exec()

    def _window_factory(self, profile: ProfileConfig, window_id: str) -> WindowFactory:
        window_config = profile.window(window_id)

        def build() -> RuntimeWindow:
            return build_profile_window(window_config, self.engine, attachments=self._attachments.for_window(window_id))

        return build

    def _activate(self, profile: ProfileConfig) -> None:
        """Start ``profile``: its state and callbacks, theme, attachments, and window factories.

        No window is built here; the caller shows the profile's windows.
        """

        self._profile = profile
        engine = self.engine
        engine.profile.start(profile)
        self._dispatcher.dispatch(*engine.profile.set_observed(("app", "profile"), profile.id))
        theme = profile.theme
        self._unbind_theme = engine.bindings.bind(
            theme.decode,
            "theme",
            lambda values, _previous: apply_theme(
                self._app, values, base_palette=self._base_palette, base_font=self._base_font
            ),
            fallback=theme.initial,
        )
        self._attachments.start(profile)
        self._window_manager.set_factories({window.id: self._window_factory(profile, window.id) for window in profile.windows})

    def _deactivate(self) -> None:
        """Tear the running profile down: callbacks, held keys, theme, attachments, then windows.

        This is the one place a profile stops while the app keeps running.
        Held keys are released because the profile that latched them, and
        its record of the latch, are gone.
        """

        self.engine.profile.stop()
        self._keyboard.reset_state()
        if self._unbind_theme is not None:
            self._unbind_theme()
            self._unbind_theme = None
        self._attachments.stop()
        self._window_manager.close_all()
        # Until the next profile starts, a window action fails instead of building an old window.
        self._window_manager.set_factories({})

    def _switch_profile(self, arguments: ProfileSwitchArguments) -> MessageResult:
        """Tear the running profile down and send ``profile.start`` for the requested one.

        Both actions run once nothing else is waiting, so the reports of the
        closing windows reach no profile. A switch requested while one is in
        progress only replaces its target: the last one requested starts.
        """

        target = self._root.profiles.get(arguments.profile)
        if target is None:
            raise ValueError(f"No profile named {arguments.profile!r} in the root config")
        self._refuse_without_panel(target)
        if self._switching_to is not None:
            self._switching_to = target.id
            return []
        if target is self._profile:
            return []
        self._deactivate()
        self._switching_to = target.id
        return [profile_start()]

    def _start_switched_profile(self, arguments: EmptyArguments) -> MessageResult:
        """Start the profile a switch is moving to.

        Each window it shows on start is built at the position a window with
        the same ID last reported. If it fails to build, the previous profile
        starts again, with its own variables back at their defaults, and the
        failure is reported as ``action.failed``; if that fails too, the
        report is ``ProfileRollbackFailed``.
        """

        del arguments
        if self._switching_to is None:
            raise ValueError("No profile switch is in progress")
        target = self._root.profiles[self._switching_to]
        self._switching_to = None
        previous = self._profile
        try:
            self._activate(target)
            self._show_start_windows()
        except Exception as error:
            _logger.exception("Failed to build profile %s; building %s again", target.id, previous.id)
            self._deactivate()
            try:
                self._activate(previous)
                self._show_start_windows()
            except Exception as rollback_error:
                raise ProfileRollbackFailed(previous.id, target.id, error) from rollback_error
            raise
        return []

    def _refuse_without_panel(self, target: ProfileConfig) -> None:
        """Reject a switch that would leave a prepared lock-screen panel without a window."""

        if self._panel_prepared and not any(attachment.kind == "secure_input_panel" for attachment in target.attachments):
            raise ValueError(f"Profile {target.id!r} has no secure_input_panel attachment for the prepared lock-screen panel")

    def _show_start_windows(self) -> None:
        """Show the running profile's start windows where windows with their IDs last were, and a prepared panel."""

        state = self.engine.profile.state
        for window_config in self._profile.windows:
            if not window_config.show_on_start or not self._show_startup_windows:
                continue
            window = self._window_manager.get_or_create(window_config.id)
            position = state.get(("windows", window_config.id, "position"))
            if position is not None:
                window.restore_position(position["x"], position["y"])  # type: ignore[index]
            self._window_manager.show(window_config.id)
        if self._panel_prepared:
            self._window_manager.show(self._secure_input_panel_window()).set_close_enabled(False)

    def _ask_to_quit(self, reason: str) -> None:
        """Ask the running profile to confirm a quit, or quit when it does not handle quit requests."""

        if APP_QUIT_REQUESTED in self._profile.on:
            self._dispatcher.dispatch(app_quit_requested(reason))
        else:
            self._dispatcher.dispatch(app_quit())

    def _default_close(self, event: WindowCloseRequestedArguments) -> MessageResult:
        """Apply Qt's close rule unless the window turned it off with ``default_close``.

        Closing the window closes it; closing the last visible window asks to
        quit instead. Profile handlers for ``window.close_requested`` run too.
        """

        window = self._window_manager.get(event.window_id)
        # A window that was never built has no current values yet, so it follows its load-time ones.
        default_close = (
            window.default_close if window is not None else self._profile.window(event.window_id).values.initial.default_close
        )
        if not default_close:
            return []
        others_visible = any(
            window.isVisible() for window in self._window_manager.all_windows() if window.window_id != event.window_id
        )
        if others_visible:
            return [window_close(event.window_id)]
        self._quit_controller.request_quit("window_closed")
        return []

    def _quit(self, arguments: AppQuitArguments) -> MessageResult:
        """Shut down; the action runs once nothing else is waiting, so every earlier request finishes first."""

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

        Only prepare and release change whether the panel is prepared. A
        prepared panel is shown again, in case the profile hid or closed its
        window. Keyboard output that cannot start fails the preparation, so
        the supervisor hears ``ERROR`` instead of a panel that cannot type.
        """

        del arguments
        window_id = self._secure_input_panel_window()
        if self._panel_prepared:
            self._window_manager.show(window_id).set_close_enabled(False)
            return [secure_input_panel_prepared()]
        try:
            self._keyboard.start(self._dispatcher)
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
        self._panel_prepared = True
        return [secure_input_panel_prepared()]

    def _release_secure_input_panel(self, arguments: EmptyArguments) -> MessageResult:
        """Close the panel while retaining this KWin input-method connection."""

        del arguments
        window_id = self._secure_input_panel_window()
        if not self._panel_prepared:
            return [secure_input_panel_released()]
        self._panel_prepared = False
        try:
            self._keyboard.reset_state()
        finally:
            self._window_manager.close(window_id)
        return [secure_input_panel_released()]
