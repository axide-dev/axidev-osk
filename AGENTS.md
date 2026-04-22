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

The Lua configuration layer is not implemented yet. That does not reduce its importance as a design constraint.

## Non-Negotiable Architecture Rules

1. Treat everything as a reusable component.
2. Do not hardcode the assumption that the app will always have one window or one layout.
3. Keep layout definition separate from widget construction.
4. Keep widget construction separate from process orchestration and backend/input logic.
5. Prefer composition through data and registries over special-case window subclasses.
6. New APIs should be designed so a future Lua config can describe and assemble them.

## Mental Model

- Buttons are components.
- Grids are components that place buttons or other controls.
- Windows are components/surfaces that host one or more grids.
- One main process coordinates windows, services, state, and future config loading.

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

## Preferred Direction For New Work

- Prefer data-driven builders over handwritten widget trees.
- Prefer generic containers over layout-specific logic inside window classes.
- Prefer registries/factories over `if` ladders tied to one known surface.
- Prefer interfaces that allow multiple instances of the same window/surface type.
- Prefer names that describe reusable concepts like `surface`, `grid`, `panel`, `component`, or `controller` when accurate.

## Avoid

- baking the US ISO keyboard into application structure
- tying state ownership directly to one window instance
- embedding future config assumptions into ad hoc local constants
- writing new code that makes multi-window composition harder
- mixing backend emission logic into button rendering code

## Lua Readiness

The future Lua layer should be able to:

- declare windows/surfaces
- choose which grids/components appear in each surface
- define or select layouts
- control placement, behavior, and composition without rewriting Python UI code

To preserve that path, keep Python-side structures serializable, declarative where possible, and stable enough to map from config later.

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

- `fix(ui): add hot-corner window toggle and shared theme palette`
- `feat(release): add standalone app packaging`
- `refactor(ci): bump workflows to Python 3.14`

Guidelines:

- keep `type` and `scope` lowercase
- use a concrete scope when possible
- keep the subject line concise and descriptive
- prefer conventional types such as `feat`, `fix`, `refactor`, `docs`, `ci`, `build`, or `test`
