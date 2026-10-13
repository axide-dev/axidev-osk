Written by inayayousfi, typed by gpt-5.6-sol running in OpenCode and by Claude Opus 5.5 running in Claude Code.
Every call here is inayayousfi's, and no agent acted on its own.

# AGENTS.md

This file is a map of the codebase for coding agents and humans: where things belong and which rules hold everywhere. What a module does is written in its docstrings, not here.

## Intent

Axidev OSK is an engine for on-screen input surfaces, and this codebase is the engine. The engine is a set of services that talk only through one queue and its dispatcher: events report what happened, actions request an effect, and no service calls another directly. Follow this strictly. It keeps every part replaceable, which is what lets this accessibility tool be customized as far as possible, and it keeps platform-specific details inside the services, out of every profile.

The keyboard you see when you start it is not built into the engine: it is the default profile, an ordinary configuration. Anything a profile can express with the engine's building blocks must be possible without changing the engine.

`src/axidev_osk/python_defaults/` holds the `axidev_osk` helpers, the standard library, and the default profile. It is temporary: a Lua layer outside this codebase will replace it, so the engine must not depend on it or assume Python. Only `app.py` reaches into it, to load the bundled config.

## The Three Layers

- The engine is everything under `src/axidev_osk/` except `python_defaults/`. It owns windows, widgets, the message queue, central state, platform integration, keyboard output, and process lifecycle. It knows no layout, no key behavior, and no profile policy.
- The standard library, `python_defaults/axidev_osk/std/`, holds keyboard conventions built only from the `axidev_osk` builders and actions. It is ordinary profile code that ships with the engine.
- A profile is a root config map. The bundled one is `python_defaults/default_profile.py`, and `tests/test_default_profile.py` holds it to the original keyboard's measurements.

When you add something, ask whether a profile author should be able to change it. If yes, it belongs in a profile or in the standard library, not in the engine.

## Rules

- A profile is plain data (maps, lists, strings, numbers, booleans, `None`) plus functions, the same values Lua tables and functions produce. A key set to `None` counts as absent, as a Lua table has no key set to `nil`.
- The `axidev_osk` helpers only build those maps. The engine decodes them in `config/profile.py`, rejects unknown keys with the full config path, and checks every profile of the root config, not only the active one.
- A binding is `fn(state) -> value`, accepted in place of any value field. Fixed fields (IDs, kinds, references, children, placement such as grid cells, `show_on_start`, `overlay`, `chrome`) stay plain values and reject a function.
- A callback is `fn(ctx, event) -> [actions]`. It reads `ctx.state`, receives the event as plain data, and returns actions as plain maps. It never touches widgets, services, or backends.
- Functions live in the function registry; messages carry only their IDs.
- Everything that crosses a subsystem boundary goes through the one queue in `runtime/dispatcher.py`. Events report what happened; actions request an effect. Both carry a lowercase dot-separated name and native data only, never Qt objects, backend objects, callables, or dataclass instances.
- Every message name is registered with a decoder before use. A handler returns follow-up messages instead of calling another subsystem directly.
- Handlers run only on the dispatcher's owner thread. Other threads, and Qt event handlers, hand what they observe to `dispatcher.post`.
- A failure is reported, not raised through the queue: a failing action becomes `action.failed`, a failing callback or binding becomes `callback.failed`, and the queue continues.
- Durable state lives in the declared variables of `runtime/state.py`. A variable is declared where its lifetime belongs: the root config's `state` for values every profile shares, a profile's `state` for values that reset when it starts, `std` modules' `STATE` for library values, and `OBSERVED_VARIABLES` for what the engine observes. Profiles read observed variables but never set them.
- Widgets render state and are never its source of truth. Only momentary visual details, such as a pressed look, stay in Qt.
- The engine owns no colors or font families: a profile's `theme` and an attachment's options carry them.
- Buttons never take keyboard focus: an on-screen keyboard must not steal typing from the target app.
- A widget property the engine sets is listed in `widget_properties.py`, which both sets and reserves it; a profile style cannot set it.
- Profile switching, quit sequencing, the lock-screen panel, and display recovery stay in the engine's lifecycle code; profiles only request them through actions.

## Where Things Live

- `runtime/dispatcher.py`: the queue and `action.failed`.
- `runtime/profile_runtime.py`: state actions, `state.changed`, `callback.failed`, and binding tracking.
- `runtime/engine_messages.py`: messages the engine handles itself: keyboard, processes, logging, and observations.
- `runtime/timers.py`: timers profiles start and cancel.
- `runtime/app_messages.py`: messages the application runtime handles or sends.
- `nodes/`: node kinds and their events. `attachments/`: attachment kinds.
- `config/`: decoding of root configs and state declarations.
- `python_defaults/`: the `axidev_osk` helpers, the standard library, and the bundled config.

## How To Add Things

A node kind. Register a `NodeKind` in `nodes/kinds.py` with its build and apply functions and its callback fields mapped to event names. Read bindable values in `decode_options`, fixed fields in `decode_structure`, the fields its children are placed with in `decode_child_placement`, and checks against its children in `check_options`. The builder emits events through `builder.emit` and never decides what a press means. Add the `axidev_osk` builder and a test next to `tests/test_nodes.py`.

An attachment. Add its options record, with its defaults, and its decoder in `attachments/__init__.py`, and register it in `register_builtin_attachments` with its `attach` step. Its options are values a profile may bind, so it owns no state and needs no setter action. Set its `limit` when at most one fits a window or a profile. Add the `axidev_osk` builder and a test in `tests/test_attachments.py`.

An action or event. Write an arguments record, a decoder, and a constructor where Python code sends it, and register the name where the owning subsystem registers its messages. An event that reports an observation writes its observed variables with `set_observed`. Add the `axidev_osk` action builder if profiles should send it.

A standard-library helper. Write it in `python_defaults/axidev_osk/std/` using only `axidev_osk` builders and actions. Take an `opts` map and merge it last with `axidev_osk.merge`, so any field can be overridden. Declare library state in the module's `STATE`; react to events through `std.with_handlers`. Test it in `tests/test_std_library.py`.

A profile change. Edit `python_defaults/default_profile.py`. If you change the default keyboard on purpose, update the expected data in `tests/test_default_profile.py` in the same change and say so in the PR.

## Avoid

- Layout, legend, latch, or prompt logic anywhere outside `python_defaults/` or a profile.
- Services, widgets, or backends calling each other directly when a message can carry the request.
- Callables, Qt objects, or dataclass instances inside queue messages or profile state.
- Engine code that assumes one window, one keyboard, or one profile.
- Shared runtime state hidden in a reusable widget, layout, or closure.
- Compatibility shims for removed APIs; update the callers instead.
- Describing a module's behavior in this file; write it in the module.

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
