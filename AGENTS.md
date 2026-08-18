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
7. Runtime subsystems should communicate through the central event/command queue, not direct cross-subsystem calls.
8. Durable application state belongs to the main process/runtime state store, not individual widgets, components, or Lua globals.
9. Services, UI widgets, backend adapters, timers, and platform integrations must not call window managers, widgets, backends, Lua callbacks, or other subsystems directly when a runtime event or command can represent the interaction.

## Mental Model

- Buttons are components.
- Grids are components that place buttons or other controls.
- Windows are components/surfaces that host one or more grids.
- One main process coordinates windows, services, state, queues, and future config loading.
- UI, backend, Lua, timers, and app controls are event producers/consumers connected through the queue.

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
  Event queue ownership, command routing, callback scheduling, state store updates, and subsystem boundaries.

## Preferred Direction For New Work

- Prefer data-driven builders over handwritten widget trees.
- Prefer generic containers over layout-specific logic inside window classes.
- Prefer registries/factories over `if` ladders tied to one known surface.
- Prefer interfaces that allow multiple instances of the same window/surface type.
- Prefer names that describe reusable concepts like `surface`, `grid`, `panel`, `component`, or `controller` when accurate.
- Prefer event/command messages over direct calls between UI, backend, Lua, and application orchestration.
- Treat runtime events and commands as the default integration boundary between subsystems; direct calls are acceptable only inside one subsystem's own implementation or when adapting an event/command in the main runtime.
- Prefer main-owned state updates that can be reset, replayed, logged, and cleaned up during config reloads or profile switches.

## Avoid

- baking the US ISO keyboard into application structure
- tying state ownership directly to one window instance
- tying durable state ownership directly to one component, widget, layout instance, or Lua closure
- embedding future config assumptions into ad hoc local constants
- writing new code that makes multi-window composition harder
- mixing backend emission logic into button rendering code
- letting UI widgets directly invoke backend services or Lua callbacks when an event can be routed through the queue instead
- letting services directly invoke window managers, windows, widgets, backend adapters, or other services instead of emitting a runtime event or command
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

The target runtime architecture is queue-driven:

- UI widgets emit interaction events into the queue.
- Backend/input services emit observed input or status events into the queue.
- Timers, app controls, profile switching, and config reloads emit events into the queue.
- The main runtime consumes ordered events, updates the main-owned state store, routes Lua callback work to the Lua actor, and applies returned commands through the queue.
- Lua callbacks do not directly mutate widgets, backend objects, or durable state. They receive context and event objects, then return or enqueue commands.

Use this model even when the current implementation is still simpler. New work should move the app toward explicit events, commands, and state-store updates rather than direct object-to-object coupling.

When a subsystem observes something, it should emit an event DTO. When a subsystem wants something to happen, it should dispatch a command DTO. The main runtime/orchestration layer owns translating those events and commands into concrete calls on window managers, services, state stores, and platform adapters. Do not wire services directly to windows or window managers, and do not wire UI components directly to backend services, unless the call remains entirely inside the same subsystem and cannot reasonably cross the runtime event/command boundary.

Durable state should be namespaced by app/profile/window/layout/component identity, but owned centrally by the main process. Components render state snapshots and emit events; they should not be the source of truth for application state. Profile switches, config reloads, and runtime resets should be able to cleanly discard all non-preserved state from this central store.

Callbacks should be treated as deferred/asynchronous by default. Callback ordering must remain deterministic through the queue, and callbacks should be able to cancel or replace default behavior through explicit event/command APIs.

User configs should be loaded from standard locations such as `XDG_CONFIG_HOME` or `~/.config` on Unix-like systems, and the usual per-user config location on Windows. Bundled configs should be used as fallback defaults and examples when user config is missing or invalid.

For more detailed Lua config and runtime architecture direction, refer to GitHub issue #8: `Define Lua config architecture`.

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
