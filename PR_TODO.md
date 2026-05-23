# PR TODO: Issue #9 Runtime Architecture Refactor

Issue: https://github.com/axide-dev/axidev-osk/issues/9

PR: https://github.com/axide-dev/axidev-osk/pull/10

## Scope Guardrails

- [x] Keep this PR architecture-only.
- [x] Do not add user-facing features.
- [x] Do not change packaging or release infrastructure.
- [x] Keep the only intended user-facing change to wording: `on-screen keyboard` -> `OSK`.
- [x] Re-check before merge that no behavior, visual, hot-corner UX, packaging, or layout changes were introduced accidentally.

## Highest Priority Review: No Duplication, Modular Runtime, Queue-Ready IDs

- [x] Treat this section as the blocking review checklist for PR #10.
- [x] Confirm every behavior has exactly one implementation path after the refactor: one generic window builder, one prompt component path, one keyboard grid path, one hot-corner service/controller path, one keyboard service/backend path.
- [x] Confirm no old feature-specific implementation remains in parallel with the new modular path. A refactored behavior must replace the old behavior, not wrap or duplicate it.
  Audit note: startup windows flow through `WindowManager`/`build_window`; prompts flow through `PromptConfig` plus the prompt component and transient generic windows; the keyboard grid flows through `KeyboardGridConfig`/`KeyboardWidget` plus key/spacer builders; hot corner flows through `HotCornerService`/`HotCornerWindowToggleController` to `HotCornerTriggered` and window commands; backend access flows through `KeyboardService` command handlers. Stale-reference search found no references to removed dedicated window/widget/layout modules.
- [x] Confirm reusable components do not own application policy. Components should render config/state snapshots and emit runtime DTOs; runtime/services should apply effects.
  Audit note: component search found prompt buttons still hid their hosting window after dispatching `PromptResolved`. That lifecycle effect was removed; prompt components now only emit the resolution event, and the runtime prompt flow closes transient prompt windows after the waiter resolves. Keyboard grid state remains local interaction/view coordination plus runtime event/command emission; backend effects still go through dispatcher commands and `KeyboardService`.
- [x] Confirm UI-to-runtime communication uses event/command DTOs rather than direct cross-subsystem calls. Direct service calls from widgets should be removed or justified as a temporary boundary with a TODO.
- [x] Confirm the synchronous dispatcher is queue-shaped: callers dispatch events/commands and do not depend on immediate handler return values.
- [x] Confirm command handlers are registered through the runtime/handler registry rather than hidden inside unrelated objects where possible. Current review focus: default keyboard command handlers in `Dispatcher.bind_context`.
- [x] Confirm deterministic IDs flow through windows, surfaces, layouts, components, state namespaces, Qt dynamic properties, logs, events, and commands.
- [x] Confirm all config/runtime IDs are produced by `runtime/identity.py`. Real config builds should not depend on helper fallbacks such as `component_id or key_id or label`.
- [x] Confirm duplicate IDs are validated at every config composition boundary, not only in the US ISO grid.
- [x] Confirm tests do not preserve duplicated production behavior. Current review focus: `_TestRuntime._handle_hot_corner_triggered` mirrors production hot-corner window-toggle routing.
- [x] Confirm naming does not preserve the old hardcoded-window mental model. Current review focus: `KeyboardWidget` may be acceptable as a component implementation name; `MainWindowLayoutTests` should likely be renamed.
- [x] Confirm state ownership is central enough for future config reload/profile switching. Local Qt interaction state is acceptable; durable app state should be in `StateStore` or service-owned runtime state with explicit reset semantics.

## Duplicate Feature Audit

- [x] Confirm old dedicated window modules are not duplicated beside the runtime window builder: `application/main_window.py` and `application/confirm_window.py` are removed in this branch.
- [x] Confirm old keyboard widget/button modules are not duplicated beside the componentized path: `components/keyboard_widget.py`, `components/key_button.py`, and `components/keyboard_metrics.py` are removed in this branch.
- [x] Confirm bundled US ISO layout is represented once through config data: `config/defaults/us_iso.py` replaces the old `layouts/us_iso.py` path.
- [x] Confirm no extra user-facing windows, layouts, settings, profiles, palettes, or Lua/config-loading features were introduced.
- [x] Confirm packaging files are untouched by this branch.
- [x] Re-check duplicate imports and stale names before final review: no references should remain to removed modules or dedicated window classes.
- [x] Decide whether stale test naming such as `MainWindowLayoutTests` should be renamed to avoid preserving the old mental model.

## Issue #9 Acceptance TODO

- [x] Verify startup still builds the same keyboard overlay through the generic window builder.
- [x] Verify quit confirmation is a normal prompt window built from config, with no dedicated confirm-window class.
- [x] Verify keyboard layout parity tests cover current US ISO rows, dense columns, nav block, function row, and key sizing.
- [x] Verify components expose the required Qt dynamic properties, including `componentType`, `componentId`, `keyId`, `ioKey`, `interactionState`, `latched`, `pressed`, `profile`, and `layout` where applicable.
- [x] Verify widgets do not directly call backend services; backend access should flow through `Context`, dispatcher commands, and services.
- [x] Verify durable state lives in the runtime state store, not as the source of truth inside reusable widgets/components.
- [x] Verify hot corner remains isolated and only crosses into the runtime through explicit callbacks/events.
- [x] Verify deterministic IDs are computed only in `runtime/identity.py` and duplicate IDs fail validation clearly.
- [x] Verify platform branching is contained in dedicated low-level platform/overlay/permission modules and not spread through higher-level orchestration.
- [x] Verify public modules, classes, functions, and DTO fields have consistent docstrings and type hints.
- [x] Verify user-visible `on-screen keyboard` wording has been replaced with `OSK`, while internal package names and metadata stay unchanged per issue scope.
- [x] Run the full test suite locally before merge.

Current local validation status: `pytest` remains unavailable in this shell (`python -m pytest` reports `No module named pytest`). `python -m compileall src tests` and `PYTHONPATH=src python -m unittest discover -s tests` pass locally; unittest currently runs 63 tests.

## Out Of Scope For This PR

- [ ] Do not implement Lua config parsing/loading.
- [ ] Do not implement the async queue, worker thread, or Lua actor.
- [ ] Do not add profile switching UX or runtime reload/reset commands.
- [ ] Do not add new layouts, windows, components, or hot-corner UX changes beyond refactoring existing behavior.
- [ ] Do not rename internal package names, paths, symbols, or packaging metadata solely for the `OSK` wording change.
