Written by inayayousfi, typed by gpt-5.6-sol running in OpenCode and by Claude Opus 5.5 running in Claude Code.
Every call here is inayayousfi's, and no agent acted on its own.

# AGENTS.md

This file explains how Axidev OSK is built and how to extend it. It is written for humans and coding agents working in this repository.

## Active Work

The runtime is being purified into an engine of building blocks plus Python defaults that a Lua layer will later replace. `PURIFICATION_PLAN.md` at the repository root holds the settled decisions, the target architecture, and step progress. Read it before changing runtime, config, components, windows, services, or bundled defaults, and do not reopen its settled decisions without a new reason.

## Intent

Axidev OSK is an engine for on-screen input surfaces. The keyboard you see when you start it is not built into the engine. It is the default profile, an ordinary configuration that happens to describe a US ISO keyboard. Anything a profile can express with the engine's building blocks should be possible without touching Python: other layouts, several windows, keys that do something other than type, small tools, odd experiments.

Profiles are written in Python today, inside `src/axidev_osk/python_defaults/`. They will be written in Lua later. The engine does not care which language produced a profile, so nothing in it may assume Python.

## The Three Layers

The engine is everything under `src/axidev_osk/` except `python_defaults/`. It owns windows, widgets, the message queue, central state, platform integration, keyboard output, and process lifecycle. It knows no layout, no key behavior, and no profile policy.

The standard library, `python_defaults/osk/std/`, holds keyboard conventions built only from engine building blocks: letter keys whose legend follows Shift and Caps Lock, latching modifiers, lock keys lit from the system, the Ghost button, window toggles, prompt windows. It is ordinary profile code that ships with the engine.

A profile is a root config map. The default one, `python_defaults/default_profile.py`, rebuilds the bundled keyboard with the standard library. It is also the parity target for the Lua port: `tests/test_default_profile.py` checks it against measurements taken from the original built-in keyboard.

When you add something, ask whether a profile author should be able to change it. If yes, it belongs in a profile or in the standard library, not in the engine.

## Profiles Are Data Plus Functions

A root config looks like this:

```python
osk.config(
    active_profile="default",
    profiles={
        "default": osk.profile(
            state={"cow_text": ""},
            theme={"qss": "..."},
            windows=[osk.window(id="pad", title="Pad", content=osk.grid(id="keys", children=[...]))],
            attachments=[osk.dwell(id="pad-dwell", window="pad")],
            on={"hot_corner.triggered": on_corner},
        )
    },
)
```

Everything in it is plain data (maps, lists, strings, numbers, booleans, `None`) plus functions, the same values a Lua table and Lua functions produce. The `osk` helpers in `python_defaults/osk/` only build those maps. The engine decodes them in `config/profile.py`, using a decoder per node kind and attachment kind, and rejects unknown keys with the full config path in the error.

Two kinds of function appear in a profile.

A binding is `fn(state) -> value`, given for a node property such as `label` or `latched`. The runtime records which state paths the binding read and re-runs it only when one of them changes, then applies the new value to the widget.

A callback is `fn(ctx, event) -> [actions]`, given for a node event (`on_press`, `on_release`) or in the profile's `on` table. It receives `ctx.state`, a read-only view of state, and the event as plain data. It returns actions as plain maps, for example `osk.window.show("pad")`. It never touches widgets, services, or backends directly. A callback that raises produces `callback.failed` and the queue continues.

Functions are stored in a registry, and queue messages only ever carry their IDs.

## Messages And The Queue

Everything that crosses a subsystem boundary goes through one first-in, first-out queue owned by `runtime/dispatcher.py`. An event reports something that happened (`input.key`, `button.pressed`, `hot_corner.triggered`). An action requests an effect (`keyboard.down`, `window.show`, `state.set`). Both carry a lowercase dot-separated name and native data only, never Qt objects, backend objects, callables, or dataclass instances.

Every name is registered with a decoder before use. Built-in messages also have typed constructors so pyright checks call sites. Handlers return follow-up messages, which the dispatcher appends after the current one. A handler must not call another subsystem directly when a message can express the request.

The dispatcher only drains on the thread that created it, which is the Qt thread in the app. Producers on other threads, such as the keyboard listener, can dispatch freely: their messages wait in a locked inbox until `QtDispatcherWake` schedules a drain on the Qt thread. Handlers therefore never run on producer threads.

An unknown action, invalid arguments, or a failing action handler is logged and produces `action.failed` with the action name, arguments, stage, exception type, and message. A failing event handler is logged and the remaining handlers for that event are skipped. The dispatcher warns every 10,000 messages processed in one drain but does not stop, so an action that keeps producing work can keep the UI busy.

Where messages are defined:

- `runtime/events.py` and `runtime/actions.py`: engine lifecycle, windows, hot corners, displays, drag, lock-screen panel, `app.quit`.
- `runtime/engine_messages.py`: keyboard effects and observations, processes, logging, quit requests, permission setup.
- `runtime/profile_runtime.py`: `state.set`, `state.changed`, `callback.failed`.
- `nodes/kinds.py`: node events such as `button.pressed`.
- `attachments/runtime.py`: `dwell.set_enabled`.

## State

Durable state lives in one tree, `runtime/state.py`, owned by the runtime. Profiles read it through views (`s.shift`, `s.input.keys.A`, `s["input"]["keys"]["."]` for names containing dots) and change it only with `state.set`. A missing value reads as `None`, the way Lua reads `nil`, and setting a value to `None` removes it. Paths are dot-separated strings or lists of segments when a segment comes from a name that may contain a dot.

Some roots are written by the engine from observations and are read-only to profiles: `input.keys.<key>`, `input.locks.capslock` and `numlock`, `keyboard.ready` and `keyboard.status`, `windows.<id>.visible` and `minimized`, `dwell.<id>.enabled`. The standard library keeps its own state under `std`. Everything else belongs to the profile, and the profile's `state` map gives its starting values.

Widgets render state; they are never its source of truth. Only purely visual, momentary details stay local to Qt, such as a button's pressed look while the mouse is down.

## Building Blocks

Node kinds are the curated widgets a profile composes: `window` (top level), `grid`, `box`, `stack`, `button`, `label`, `spacer`. Each kind declares its bindable properties, its callback fields and the events they map to, how its options decode, how it builds a widget, and how a property value is applied. Every built widget carries `componentType` and `componentId` properties, and profile style hooks (`object_name`, `classes`, `properties`, `qss`) are applied to it, so QSS can target any of them. Buttons never take keyboard focus, because an on-screen keyboard must not steal typing from the target app.

Attachments are Python-owned features that run their own loop and are attached to a target by reference: `dwell` and `pointer_locator` on a window, `hot_corners` for the screen, `secure_input_panel` naming the window shown on the Plasma lock screen. A profile sets their options and talks to them through actions, events, and observed state. They do not call profile functions per pointer movement.

Engine effects include `keyboard.down/up/tap/type_text`, window actions (`show`, `hide`, `close`, `move_by`, `set_opacity`, `block_input`, `unblock_input`), `dwell.set_enabled`, `state.set`, `process.spawn` with an argument list (never a shell string), `log.info/warn/error`, `app.quit`, and `linux.open_permission_setup`.

Lifecycle stays in Python: quit sequencing (SIGTERM quits without asking; other quit requests become `app.quit_requested` when the profile handles it), the lock-screen supervisor protocol, display recovery, and the background lane where spawned programs report `process.exited`.

## How To Add Things

A node kind. Write its build and apply functions and register a `NodeKind` in `nodes/kinds.py` (or a new module called from `register_builtin_nodes`). Declare bindable properties with `PropertySpec`, map callback fields to event names, and decode options with `ConfigReader`, which rejects unknown keys for you. The builder emits events through `builder.emit(event_name, node.id)` and never decides what a press means. Add a matching builder function in `python_defaults/osk/__init__.py`, then a test next to `tests/test_nodes.py`.

An attachment. Add its options record and decoder in `attachments/__init__.py` and register it in `register_builtin_attachments`. If it acts on a window, extend `WindowAttachments` and install it in `build_profile_window`. If it owns state, write it as observed state under its own root and expose an action to change it, as dwell does. Validate its references in `AttachmentRuntime.start`. Add the `osk` builder and a test in `tests/test_attachments.py`.

An action or event. Pick a lowercase dot-separated name, write an arguments record, a decoder, and a typed constructor, and register the name where the owning subsystem registers its messages. Add the `osk` action builder if profiles should send it. An event that reports an observation profiles should read later also writes runtime-owned state, and that handler is installed before profiles start so callbacks see current state.

A standard-library helper. Write it in `python_defaults/osk/std/` using only `osk` builders and actions. Take an `opts` map and merge it last with `osk.merge`, so any single field can be overridden. Keep library state under `std`. Test it in `tests/test_std_library.py`.

A profile change. Edit `python_defaults/default_profile.py`, or build a new root config with the same helpers. If you change the default keyboard on purpose, update the expected data in `tests/test_default_profile.py` in the same change and say so in the PR.

## Avoid

- Layout, legend, latch, or prompt logic anywhere outside `python_defaults/` or a profile.
- Services, widgets, or backends calling each other directly when a message can carry the request.
- Callables, Qt objects, or dataclass instances inside queue messages or profile state.
- Engine code that assumes one window, one keyboard, or one profile.
- Shared runtime state hidden in a reusable widget, layout, or closure.
- Compatibility shims for removed APIs; update the callers instead.

## Checks

Run these before pushing:

```text
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests
python -m flake8 --select=F,E9,W6 src
python -m pyright
```

## Contribution Workflow

Prefer landing work through pull requests.

The project is already in a reasonably good state, so contributors and agents should avoid casual direct-to-main style changes unless explicitly asked to do so. Small fixes are still preferred as PRs when practical, because review helps protect architecture, packaging, and cross-platform behavior.

PR guidance:

- keep each PR focused on one problem or one cohesive improvement
- call out architectural impact explicitly when changing the engine, node kinds, attachments, messages, or the default profile
- avoid bundling unrelated cleanup into feature work
- note platform-specific behavior changes clearly when Windows, X11, or Wayland behavior is affected

## Commit Message Style

Prefer the commit style already dominant in the repository:

```text
type(scope): short imperative summary
```

Examples from current history:

- `feat(release): add standalone app packaging`
- `refactor(ci): bump workflows to Python 3.14`

Guidelines:

- keep `type` and `scope` lowercase
- use a concrete scope when possible
- keep the subject line concise and descriptive
- prefer conventional types such as `feat`, `fix`, `refactor`, `docs`, `ci`, `build`, or `test`
