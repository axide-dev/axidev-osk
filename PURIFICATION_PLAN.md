# Purification Plan

This file records the agreed plan for turning Axidev OSK into a pure engine of building blocks configured by profiles. It is the source of truth for that work until the work is finished.

Remove this file when the Lua layer has replaced `src/axidev_osk/python_defaults/` and that directory no longer exists.

## Goal

Python ships an engine, not a keyboard. The engine exposes building blocks: nodes, attachments, actions, events, observed state, and lifecycle. It contains no keyboard layout, no key behavior, and no profile policy.

A profile is described only by plain data (maps, lists, strings, numbers, booleans, null) plus functions. That shape matches Lua tables and Lua functions exactly. Until the Lua layer exists, profiles and the standard library are written in Python inside `src/axidev_osk/python_defaults/`. Switching to Lua later means installing lupa, loading `.lua` files that produce the same values, and deleting `python_defaults/`. The engine does not change.

The only things that ship are the engine, the standard library (`osk.std`), and a default profile that rebuilds today's US ISO keyboard.

## Settled Decisions

Each decision below was made by the project owner. Do not reopen one without a new reason.

1. No Lua in the purification PR. Purify Python first so that a Lua loader can replace the Python defaults by reading the same values.

2. Bindings and callbacks are Python functions now and Lua functions later. The engine never assumes which language produced them.

3. Node properties that follow state use function bindings: `fn(state) -> value`. The runtime records which state keys a binding read and re-runs it only when one of those keys changes.

4. Callbacks have the shape `fn(ctx, event) -> [actions]`. `ctx` exposes read-only state and nothing else that can cause effects. Callbacks return actions as plain data. They never touch widgets, services, or backends.

5. Hooks are deleted. Nodes have no default behavior, so a callback is the behavior. Reuse and override happen through ordinary function composition and per-field `opts` overrides.

6. Lua reaches Qt only through curated primitives with our own names and state binding. There is no generic Qt bridge.

7. Feature primitives with their own loop (dwell clicking, pointer locator, hot corners, secure input panel) stay in Python as attachments. A profile attaches them to a real node by reference and configures their options. They do not call per-movement callbacks.

8. Keyboard conventions (letter keys, modifiers, latching, legends, ghost, window toggles, prompts) live in a standard library written in the config language, not in the engine. In this PR the library is Python code inside `python_defaults/`.

9. Keystroke observations reach whatever profile the process runs. The engine makes no lock-screen exception because each process has its own profile.

10. Durable state stays in the central runtime store. Widgets render state and emit events. The queue carries native data and function IDs, never functions or live objects.

## Target Architecture

### Config Shape

- The root config holds `profiles` and `active_profile`.
- A profile holds `state` (initial values), `windows`, `attachments`, and `on` (callbacks for any registered event).
- Every node is a map with `kind`, `id`, options, `style` (object name, classes, properties, QSS), function bindings, and callbacks.
- Each node kind and attachment kind registers a decoder that validates its map into a typed record. Bundled defaults and future Lua configs use the same decoders.
- `osk.*` helpers only build maps. `osk.merge(defaults, opts)` lets a caller override any single field.

### Functions

- Callbacks: `fn(ctx, event) -> [actions]`.
- Bindings: `fn(state) -> value`, re-run only when a state key they read changes.
- A function registry stores callbacks and bindings. Queue messages carry their IDs.
- A failing callback or binding produces `callback.failed` and is logged. It never stops the queue.

### Engine Building Blocks

Nodes:

- `window`: title, opacity, overlay placement, chrome, `show_on_start`, content.
- `grid`: rows, columns, spans, cell metrics, children.
- `box`, `stack`, `button`, `label`, `spacer`.
- A button keeps Qt's instant pressed look locally. `active`, `latched`, `label`, and `visible` are bindable.

Attachments:

- `dwell` on a window.
- `pointer_locator` on a window.
- `hot_corners` with sensor settings.
- `secure_input_panel` naming the window shown on the lock screen.

Actions:

- `keyboard.down {key, mods, repeat}`, `keyboard.up {key}`, `keyboard.tap {key, mods}`, `keyboard.type_text {text}`.
- `window.show`, `window.hide`, `window.close`, `window.move_by`, `window.set_opacity`, `window.block_input {window, except}`, `window.unblock_input`.
- `dwell.set_enabled`.
- `state.set`.
- `process.spawn {argv, tag}` with an argument list, never a shell string.
- `log.info`, `log.warn`, `log.error`.
- `app.quit`.
- `linux.open_permission_setup`.

Events:

- Node events such as `button.pressed` and `button.released`.
- `input.key {key, text, modifiers, pressed}` for every observed keystroke, in order.
- `hot_corner.triggered`, `display.configuration_changed`.
- `app.quit_requested`, `window.close_requested`.
- `keyboard.permission_required`, `keyboard.reset`.
- `process.exited {tag, code}`.
- `window.drag_started`, `window.drag_ended`, `pointer.motion_observed`.

Observed state, written by the runtime and read-only to profiles:

- `input.keys.<name>`, `input.locks.capslock`, `input.locks.numlock`.
- `windows.<id>.visible`, `windows.<id>.minimized`.
- `dwell.<id>.enabled`.

Lifecycle that stays in Python:

- Quit sequencing, including SIGTERM without confirmation.
- The lock-screen supervisor protocol.
- Display recovery.
- The owner-thread queue drain.
- A background lane where spawned programs report `process.exited` through the queue.

### Standard Library (`osk.std`)

- `keys`: `letter`, `shifted`, `modifier` (latching, one-shot or held), lock-lit keys such as Caps. Library state lives under `std.*`.
- `windows`: `toggle`, `ghost_button`.
- `prompts`: quit and Linux-permission prompt builders.
- Every builder takes `opts` to override any field and uses only engine building blocks.

### Default Profile

- US ISO layout, cell metrics, and theme QSS written with `osk.std`.
- Ghost, Dwell, hot corners, and prompts wired through the profile `on` table and callbacks.
- Parity tests cover keys, output, latching, legends, Caps, Ghost, Dwell, corners, and prompts.

### Deleted From The Engine

- Behavior kinds, key modes, hooks, and `BehaviorBinding`.
- State tags, `KeyDisplay`, `_STATE_TAGS_BY_KEY`, and automatic Shift for letters.
- The keyboard grid's function-row, navigation, and dense-column logic.
- `window.toggle_opacity`, hot-corner routing policy, and the prompt modal loop.
- Fixed root fields (`quit_prompt`, `linux_permission_prompt`, `keyboard_window_id`, `hot_corner`) and `Context.keyboard`.
- Key-output registration. Keys are addressed by name.
- `config/defaults/us_iso.py` as engine code.

## Directory Rule

`src/axidev_osk/python_defaults/` contains everything that the Lua layer will replace: the `osk` helper surface used by profiles, the `osk.std` library, and the default profile. Code outside that directory must not contain keyboard layouts, key behavior, or profile policy. When adding something, ask whether a profile author should be able to change it. If yes, it belongs in `python_defaults/` or in a profile, not in the engine.

## Steps

Each step keeps the full test suite, flake8, and pyright passing.

- [x] 0. Record this plan and point `AGENTS.md` to it.
- [x] 1. Config maps, decoders, function registry, bindings with read tracking, profile `on` table.
- [x] 2. Observed state, `input.key`, keyboard actions, `process.spawn` with its background lane, log actions.
- [x] 3. Generic nodes and profile windows, built alongside the old keyboard grid. The app switches to them in step 5, and step 7 deletes the old grid and key components.
- [x] 4. `osk.std` library in `python_defaults/` with its own tests.
- [x] 5. Default profile on `osk.std` with parity tests. The app does not load it yet.
- [ ] 6. Attachments (dwell, pointer locator, hot corners, secure input panel) take references and options, each tested on its own.
- [ ] 7. Switch the app to the default profile in one step: quit flow, prompts, permission flow, and lock-screen panel. Delete dead engine code. Rewrite `AGENTS.md` to explain the architecture with practical guides for adding node kinds, attachments, actions, events, library helpers, and profiles.

## After This PR

- Update GitHub issue #8 to match these decisions. Show the exact text to the project owner before editing.
- Update the PR #36 description.
- Build the Lua layer: load `.lua` profiles through the same decoders, port `osk.std` and the default profile to Lua, then delete `python_defaults/` and this file.
