Written by inayayousfi, typed by gpt-5.6-sol running in OpenCode.
Every call here is inayayousfi's, and no agent acted on its own.

# AGENTS.md

This file defines the architectural guardrails for humans and coding agents working in this repository.

## Intent

Axidev OSK should evolve into a modular composition system for on-screen input surfaces.

The current app is a keyboard overlay, but that is only the first concrete surface. The architecture must stay flexible enough to support:

- multiple windows
- multiple layouts
- reusable grids
- reusable buttons and controls
- centralized application/process orchestration
- future Lua-driven configuration
- queue-driven runtime coordination

The Lua configuration layer is not implemented yet. That does not reduce its importance as a design constraint.

## Non-Negotiable Architecture Rules

1. Treat everything as a reusable component.
2. Do not hardcode the assumption that the app will always have one window or one layout.
3. Keep layout definition separate from widget construction.
4. Keep widget construction separate from process orchestration and backend/input logic.
5. Prefer composition through data and registries over special-case window subclasses.
6. New APIs should be designed so a future Lua config can describe and assemble them.
7. Runtime subsystems should communicate through the central event/action queue, not direct cross-subsystem calls.
8. Durable application state belongs to the main process/runtime state store, not individual widgets, components, or Lua globals.
9. Services, UI widgets, backend adapters, timers, and platform integrations must not call window managers, widgets, backends, Lua callbacks, or other subsystems directly when a runtime event or action can represent the interaction.

## Mental Model

- Buttons are components.
- Grids are components that place buttons or other controls.
- Windows are components/surfaces that host one or more grids.
- One main process coordinates windows, services, state, queues, and future config loading.
- UI, backend, Lua, timers, and app controls are event and action producers/consumers connected through the queue.

This means the current `MainWindow` is an implementation detail, not the final shape of the application.

## Desired Separation Of Concerns

When adding or refactoring code, keep these boundaries clear:

- `models/`-style concerns:
  Structured data definitions for keys, grids, surfaces, layout metadata, and future config-backed descriptions.
- `components/`-style concerns:
  Reusable visual and interaction primitives. These should not own global application policy.
- `application/`-style concerns:
  Window orchestration, overlay behavior, lifecycle coordination, environment/platform integration.
- backend/service concerns:
  Keyboard emission, config loading, registries, state synchronization, and future Lua integration.
- runtime/orchestration concerns:
  Event queue ownership, action routing, callback scheduling, state store updates, and subsystem boundaries.

## Preferred Direction For New Work

- Prefer data-driven builders over handwritten widget trees.
- Prefer generic containers over layout-specific logic inside window classes.
- Prefer registries/factories over `if` ladders tied to one known surface.
- Prefer interfaces that allow multiple instances of the same window/surface type.
- Prefer names that describe reusable concepts like `surface`, `grid`, `panel`, `component`, or `controller` when accurate.
- Prefer event/action messages over direct calls between UI, backend, Lua, and application orchestration.
- Treat runtime events and actions as the default integration boundary between subsystems; direct calls are acceptable only inside one subsystem's own implementation or when adapting an event/action in the main runtime.
- Prefer main-owned state updates that can be reset, replayed, logged, and cleaned up during config reloads or profile switches.

## Avoid

- baking the US ISO keyboard into application structure
- tying state ownership directly to one window instance
- tying durable state ownership directly to one component, widget, layout instance, or Lua closure
- embedding future config assumptions into ad hoc local constants
- writing new code that makes multi-window composition harder
- mixing backend emission logic into button rendering code
- letting UI widgets directly invoke backend services or Lua callbacks when an event can be routed through the queue instead
- letting services directly invoke window managers, windows, widgets, backend adapters, or other services instead of emitting a runtime event or action
- adding hidden shared runtime state to reusable layouts; reused layouts should instantiate fresh runtime state

## Lua Readiness

The future Lua layer should be able to:

- return one root config object with any number of profiles
- declare windows/surfaces
- choose which grids/components appear in each surface
- define layouts and instantiate fresh layout instances inside windows
- control placement, behavior, and composition without rewriting Python UI code
- attach inline Lua callbacks to component interactions and state-machine events
- cancel, replace, or extend default component behavior from callbacks
- load bundled configs and user configs through the same parser/runtime path

To preserve that path, keep Python-side structures serializable, declarative where possible, and stable enough to map from config later.

Bundled layouts such as the default US ISO keyboard should eventually be ordinary Lua files. They should act as examples and parity tests for the Lua config system, not as hardcoded Python layout knowledge.

## Queue And State Architecture

The runtime uses one synchronous first-in, first-out queue for events and actions. Producers add messages to the queue. The dispatcher drains them in order on the calling thread. A handler can return more events or actions, and the dispatcher appends those messages after the handler finishes.

### Message Contract

An event reports something that happened:

RuntimeEvent(event="component.pressed", arguments={...})

An action requests an effect:

RuntimeAction(action="window.show", arguments={...})

The name must be lowercase and dot-separated. The arguments must contain only native data that Lua and Python can exchange without live object references: null, booleans, finite numbers, strings, lists, and string-keyed maps.

Queue messages must not contain Qt objects, backend objects, Python callbacks, Lua functions, dataclass instances, or other process-local values. Use stable IDs and native data. A subsystem can resolve an ID to an object only inside the registered handler that owns that subsystem.

Configured behavior uses the same RuntimeAction shape as queued behavior. Keys, buttons, menu items, hot corners, timers, profile controls, and future Lua callbacks must not introduce parallel action formats.

### Registration And Typing

Every event and action name must be registered before use. A registration supplies an argument decoder and, for an action, its handler. Built-in definitions also provide typed argument records and typed constructors so Pyright checks repository-owned call sites. Lua-defined names remain open-ended and receive runtime checks from their registered decoders.

Duplicate registration fails by default. An explicit override replaces the whole definition, including its decoder and handler. Code that overrides a built-in name is responsible for any incompatibility with existing producers.

Handlers return an ordered list of follow-up RuntimeEvent and RuntimeAction messages. They must not call another subsystem or recursively dispatch messages. The main runtime may adapt a registered action into a concrete call on the window manager, state store, backend, or another runtime-owned service.

### Failures And Ordering

An unknown action, invalid action arguments, or an action-handler exception is logged and produces action.failed. The failure event contains the action name, original arguments, failure stage, exception type, and message.

An unknown event, invalid event arguments, or an event-handler exception is logged. The dispatcher skips the remaining handlers for that event and continues with the queue. It does not emit a second failure event, which avoids recursive failure handling.

The dispatcher warns after every 10,000 messages processed without returning. It does not stop the drain. Custom actions are allowed to produce unbounded work, so a cyclic action can keep the UI thread busy and produce unlimited logs.

### Lua Boundary

Lua tables convert recursively to the native argument map. JSON text is not the queue format. Lua-defined actions register names, decoders, and callback references through the future Lua actor. The queue stores the reference and native arguments, never the Lua function itself.

Lua callbacks are deferred by default. They receive event or action context and return events or actions to the queue. They do not mutate widgets, backend objects, or durable state directly. Cancellation, replacement, and extension of default behavior must be represented by explicit queue data rather than direct cross-subsystem calls.

### State Ownership

Durable state remains owned by the main runtime state store and is namespaced by app, profile, window, layout, and component identity. Components render state snapshots and emit events. Profile switches, config reloads, and runtime resets must be able to discard all non-preserved state without depending on widget or Lua closure lifetime.

User configs should be loaded from standard locations such as XDG_CONFIG_HOME or ~/.config on Unix-like systems, and the usual per-user config location on Windows. Bundled configs should be fallback defaults and examples when user config is missing or invalid.

For more detailed Lua config direction, refer to GitHub issue #8: Define Lua config architecture.

## Practical Rule For Contributors

When making a change, ask:

"Does this make the app more like a reusable composition system, or more like a single hardcoded keyboard window?"

If it pushes toward the second outcome, redesign it before merging.

## Contribution Workflow

Prefer landing work through pull requests.

The project is already in a reasonably good state, so contributors and agents should avoid casual direct-to-main style changes unless explicitly asked to do so. Small fixes are still preferred as PRs when practical, because review helps protect architecture, packaging, and cross-platform behavior.

PR guidance:

- keep each PR focused on one problem or one cohesive improvement
- call out architectural impact explicitly when changing windows, grids, layout models, or orchestration
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
