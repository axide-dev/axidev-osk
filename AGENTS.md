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

The standard library, `python_defaults/axidev_osk/std/`, holds keyboard conventions built only from engine building blocks: letter keys whose legend follows Shift and Caps Lock, latching modifiers, lock keys lit from the system, the Ghost button, window toggles, prompt windows. It is ordinary profile code that ships with the engine.

A profile is a root config map. The default one, `python_defaults/default_profile.py`, rebuilds the bundled keyboard with the standard library. It is also the parity target for the Lua port: `tests/test_default_profile.py` checks it against measurements taken from the original built-in keyboard.

When you add something, ask whether a profile author should be able to change it. If yes, it belongs in a profile or in the standard library, not in the engine.

## Profiles Are Data Plus Functions

A root config looks like this:

```python
axidev_osk.config(
    active_profile="default",
    profiles={
        "default": axidev_osk.profile(
            state={"cow_text": axidev_osk.var("string", "")},
            theme={"qss": "..."},
            windows=[axidev_osk.window(id="pad", title="Pad", content=axidev_osk.grid(id="keys", children=[...]))],
            attachments=[axidev_osk.dwell(id="pad-dwell", window="pad")],
            on={"hot_corner.triggered": on_corner},
        )
    },
)
```

Everything in it is plain data (maps, lists, strings, numbers, booleans, `None`) plus functions, the same values a Lua table and Lua functions produce. The `axidev_osk` helpers in `python_defaults/axidev_osk/` only build those maps. The engine decodes them in `config/profile.py`, using a decoder per node kind and attachment kind, and rejects unknown keys with the full config path in the error. Every profile in the root config is decoded and checked, not only the active one. A key set to `None` counts as absent, the way a Lua table has no key set to `nil`.

A profile's `theme` holds its stylesheet (`qss`), Qt palette colors by role (`palette`), and its font (`font`). The engine owns no colors or font families: attachments that draw, such as `hot_corners` and `pointer_locator`, take their colors as required options.

Two kinds of function appear in a profile.

A binding is `fn(state) -> value`, given in place of any value field: a node's options and style, a window's title, opacity, minimum size, `default_close`, and `input_blocked`, an attachment's options, or the theme. Fixed fields stay plain values and reject a function: ids, kinds, references such as an attachment's `window`, grid cells, children, `show_on_start`, and a window's `overlay` and `chrome`. The runtime records which state paths the bindings in one record read, and when one of them changes it decodes the whole record again and applies only the fields that differ. At load every binding runs once against the default state, so a binding that reads an undeclared path or returns an invalid value rejects the config with its path. Later, an invalid result produces `callback.failed` and the target keeps its last value.

A callback is `fn(ctx, event) -> [actions]`, given for a node event (`on_press`, `on_release`) or in the profile's `on` table. It receives `ctx.state`, a read-only view of state, and the event as plain data. It returns actions as plain maps, for example `axidev_osk.window.show("pad")`. It never touches widgets, services, or backends directly. A callback that raises produces `callback.failed` and the queue continues.

Functions are stored in a registry, and queue messages only ever carry their IDs.

## Messages And The Queue

Everything that crosses a subsystem boundary goes through one first-in, first-out queue owned by `runtime/dispatcher.py`. An event reports something that happened (`input.key`, `button.pressed`, `hot_corner.triggered`). An action requests an effect (`keyboard.down`, `window.show`, `state.set`). Both carry a lowercase dot-separated name and native data only, never Qt objects, backend objects, callables, or dataclass instances.

Every name is registered with a decoder before use. Built-in messages also have typed constructors so pyright checks call sites. Handlers return follow-up messages, which the dispatcher appends after the current one. A handler must not call another subsystem directly when a message can express the request.

The dispatcher only drains on the thread that created it, which is the Qt thread in the app. Producers on other threads, such as the keyboard listener, can dispatch freely: their messages wait in a locked inbox until `QtDispatcherWake` schedules a drain on the Qt thread. Handlers therefore never run on producer threads. A window's Qt event handlers hand what they observe to `dispatcher.post`, which uses the same inbox, so a drain never runs inside the Qt event that reported it.

An unknown action, invalid arguments, or a failing action handler is logged and produces `action.failed` with the action name, arguments, stage, exception type, and message. A failing event handler is logged and the other handlers for that event still run. An action registered with `when_idle=True`, such as `app.quit`, waits until no other message is queued or waiting in the inbox; such actions then run one at a time in the order they arrived. The dispatcher warns every 10,000 messages processed in one drain but does not stop, so an action that keeps producing work can keep the UI busy.

Where messages are defined:

- `runtime/dispatcher.py`: `action.failed`, which the dispatcher reports itself.
- `runtime/app_messages.py`: messages the application runtime handles or sends: windows, drags, displays, hot corners, the lock-screen panel, quit requests, `app.activated`, and Linux permission setup.
- `runtime/engine_messages.py`: messages the engine handles itself: keyboard effects and observations, window state, processes, and logging.
- `runtime/profile_runtime.py`: `state.set`, `state.changed`, `callback.failed`.
- `nodes/kinds.py`: node events such as `button.pressed`, registered as each kind is added.

`build_engine` registers every event name, so a profile can handle any of them. The application registers the actions that need objects it owns. `dispatcher.dispatch(*messages)` queues a whole batch before draining, so the batch keeps its order.

## State

Durable state lives in one tree, `runtime/state.py`, owned by the runtime. It is a registry of declared variables: the engine stores each value and checks it against its declared type, but it does not know what any of them mean.

A variable is declared in place inside a nested `state` map with `axidev_osk.var(type, default)`, which builds `{"var": type, "default": value}`. Types are `"boolean"`, `"integer"`, `"number"`, `"string"`, `axidev_osk.list_of(T)`, `axidev_osk.map_of(T)`, and `axidev_osk.record({...})`, whose fields are `axidev_osk.var` declarations. A scalar needs a default, a list or map defaults to empty, and a record takes its default from its fields. `config/variables.py` decodes declarations and checks values.

Where a variable is declared sets its lifetime. The root config's `state` (`axidev_osk.config(state=...)`) declares variables every profile shares, which survive a profile switch. A profile's `state` declares its own, which reset to their defaults each time it starts. Declaring a path that overlaps another declaration is rejected at load, and nothing is saved to disk.

The registry is strict. `state.set` on a path no declaration covers, or with a value of the wrong type, fails with `action.failed`. Reading an undeclared path raises, so the binding or callback reports `callback.failed`. Reading an absent entry of a declared map returns `None`, the way Lua reads `nil`. Setting a variable to `None` resets it to its default, setting a record field to `None` resets that field, and setting a map entry to `None` removes the entry along with any enclosing entries it left empty. `True` is not equal to `1`, and an integer variable rejects a boolean.

Profiles read state through views (`s.shift`, `s.input.keys.A`, `s["input"]["keys"]["."]` for names containing dots). Paths are dot-separated strings or lists of segments when a segment comes from a name that may contain a dot.

The engine declares the variables it writes from observations, and profiles can read them but not set them: `input.keys.<key>`, `input.locks.capslock` and `numlock`, `keyboard.ready`, `status`, `needs_permission_setup`, and `permission_setup_text`, and `windows.<id>.visible`, `minimized`, `position` (`x`, `y`), and `size` (`width`, `height`). `OBSERVED_VARIABLES` in `runtime/engine_messages.py` declares them through `ProfileRuntime.declare_observed`, and handlers write them with `set_observed`. A value a binding can set, such as a window's opacity or a dwell attachment's `enabled`, has no setter action and no observed copy: the variable its binding reads is its only source. The standard library declares its variables under `std`, and a profile adds them with `std.with_state`. Everything else belongs to the profile or the root config.

Widgets render state; they are never its source of truth. Only purely visual, momentary details stay local to Qt, such as a button's pressed look while the mouse is down.

## Building Blocks

Node kinds are the curated widgets a profile composes: `window` (top level), `grid`, `box`, `stack`, `button`, `label`, `spacer`. Each kind declares its bindable properties, its callback fields and the events they map to, how its options decode, how it builds a widget, and how a property value is applied. Every built widget carries `componentType` and `componentId` properties, and profile style hooks (`object_name`, `classes`, `properties`, `qss`) are applied to it, so QSS can target any of them. A node marked `passes_input_block` still takes clicks while its window has `input_blocked` set, the way the Ghost button brings a ghosted window back. A style cannot set a property the engine or the node kind sets itself, such as `componentId` or a button's `latched`. Buttons never take keyboard focus, because an on-screen keyboard must not steal typing from the target app.

Every window keeps the engine's close rule unless it sets `default_close` to false: closing the window closes it, and closing the last visible window asks to quit. A profile's own `window.close_requested` handler runs as well, so a window whose close the profile handles itself, like the default keyboard, turns the rule off.

Attachments are Python-owned features that run their own loop and are attached to a target by reference: `dwell` and `pointer_locator` on a window, `hot_corners` for the screen, `secure_input_panel` naming the window shown on the Plasma lock screen. A profile sets their options, binding any of them to state, and hears from them through events. They do not call profile functions per pointer movement.

Engine effects include `keyboard.down/up/tap/type_text`, window actions (`show`, `hide`, `close`, `move_by`), `state.set`, `process.spawn` with an argument list (never a shell string), `log.info/warn/error`, `app.quit`, and `linux.open_permission_setup`. A keyboard action that cannot run, for example because output is not ready, reports `action.failed`, and so does a window action naming a window the profile does not define.

Lifecycle stays in Python: quit sequencing (SIGTERM quits without asking; other quit requests become `app.quit_requested` with their reason, `signal`, `stdin_closed`, or `window_closed`, when the profile handles it; `app.quit` waits until no other message is queued, then shutdown closes the queue, stops the profile, and tears everything down, and a step that fails is logged without stopping the exit), the lock-screen supervisor protocol, display recovery, and the background lane where spawned programs report `process.exited`.

## How To Add Things

A node kind. Write its build and apply functions and register a `NodeKind` in `nodes/kinds.py` (or a new module called from `register_builtin_nodes`). Map callback fields to event names. Read the kind's values in `decode_options` with `ConfigReader`, which rejects unknown keys for you; every field read there accepts a binding, and `apply` receives the new options with the previous ones so it changes only what differs. Read fixed fields, such as a box's `direction`, in `decode_structure`. A kind with children also decodes the fields its children are placed with in `decode_child_placement`, the way a grid reads `cell` and a box reads `stretch`, so those fields are unknown keys under any other parent. A kind whose options must fit its children, the way a stack's `current` must name one of its pages, checks them in `check_options`, which receives the children's IDs and runs at load and on every later decode. The builder emits events through `builder.emit(event_name, node.id)` and never decides what a press means. Add a matching builder function in `python_defaults/axidev_osk/__init__.py`, then a test next to `tests/test_nodes.py`.

An attachment. Add its options record and decoder in `attachments/__init__.py` and register it in `register_builtin_attachments`. If it acts on a window, extend `WindowAttachments` and install it in `build_profile_window`. Its options are values a profile may bind, so it owns no state and needs no setter action: `AttachmentRuntime` binds them and calls its applier with each new set of options. Set the kind's `limit` to `"window"` or `"profile"` when at most one fits there: the config decoder checks every attachment's window reference and these limits in every profile at load. Add the `axidev_osk` builder and a test in `tests/test_attachments.py`.

An action or event. Pick a lowercase dot-separated name, write an arguments record, a decoder, and a typed constructor, and register the name where the owning subsystem registers its messages. Add the `axidev_osk` action builder if profiles should send it. An event that reports an observation profiles should read later also writes observed state: declare its variables with `declare_observed` and write them with `set_observed`, in a handler installed before profiles start so callbacks see current state.

A standard-library helper. Write it in `python_defaults/axidev_osk/std/` using only `axidev_osk` builders and actions. Take an `opts` map and merge it last with `axidev_osk.merge`, so any single field can be overridden. Declare library state in the module's `STATE`, which `std.with_state` merges under `std`. When the library must react to an event, add its handler to `std.with_handlers`, which profiles use to build their `on` table. Test it in `tests/test_std_library.py`.

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
