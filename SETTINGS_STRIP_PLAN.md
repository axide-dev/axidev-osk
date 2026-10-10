# Settings Strip Plan

This file records the agreed plan for the settings strip and live profile switching. It is the source of truth for that work until the work is finished. It builds on the state registry described in `PURIFICATION_PLAN.md` (settled decisions 11 to 17 and step 8), which lands first in the branch below this one.

Remove this file when the work below is merged.

## Goal

A profile can put a strip of controls at the bottom of any window: checkboxes, steppers, dropdowns, and menus. Each control reads and writes registry variables, so the profile decides what the strip shows, what it controls, and what its callbacks do. The engine adds no menu concept of its own.

The bundled config uses the strip to show the feature: the default keyboard gets a settings strip, and a second small profile gives profile switching a real target.

## Settled Decisions

Each decision below was made by the project owner. Do not reopen one without a new reason.

1. The strip is ordinary profile content placed at the bottom of a window's content, not part of the engine's title bar. It works on every backend, including those where the system draws the title bar.

2. Dropdowns and menus open as inline panels inside the window, not as Qt popups. A test on KDE Plasma Wayland showed that Qt popups fail on layer-shell windows: LayerShellQt 6.7.5 logs `Cannot attach popup of unknown type` and neither a dropdown list nor a menu appears, even with the window set as the popup's parent. Popups were not tested on the input-panel backend because it only starts when KWin launches it.

3. An inline panel grows the window. The engine shrinks the window back to its minimum size when content shrinks, the way `apply_startup_size` sizes it at show time. The same test showed a layer-shell window growing from 200x100 to 200x200 when a panel appeared and staying at 200x200 after it hid.

4. Checkboxes, steppers, dropdowns, and menus are standard-library helpers built from existing node kinds, not new engine node kinds. A checkbox is a button with a `latched` binding. A dropdown or menu is a button that flips `std.menus.<id>.open` plus a box whose `visible` binding reads it. A stepper is a pair of buttons around a label, and its minimum, maximum, and value are bindings, so linked settings can bound each other.

5. Profiles switch at runtime through `profile.switch {profile}`. The engine exposes `app.profile` and `app.profiles` as read-only variables. A switch requested from a callback runs once the queue is empty, the same way `app.quit` waits.

6. A window whose id exists in both profiles keeps its screen position through `windows.<id>.position`, and its size refits to the new content.

7. If building the new profile fails, the previous profile is rebuilt and the failure is reported.

## Engine Work

- Shrink a window back to its minimum size after its content shrinks.
- `profile.switch`, with teardown of the old profile's windows, bindings, callbacks, and attachments, then the build of the new one.
- `app.profile` and `app.profiles` as engine-declared, read-only variables.
- Keep `windows.<id>.position` across a rebuild on every backend. Layer shell places windows through margins, so each backend needs its own test.
- Rebuild the previous profile when a switch fails.

## Standard Library

- `checkbox`, `stepper`, `dropdown`, and `menu` in `python_defaults/osk/std/`, each taking `opts` merged last with `osk.merge`.
- Their state lives under `std`, declared in the registry, for example `std.menus` as a map of booleans.
- Tests in `tests/test_std_library.py`.

## Bundled Config

### Default Keyboard Strip

A strip at the bottom of the `keyboard` window holds:

- A profile dropdown listing `default` and `social`.
- An opacity stepper, 0.30 to 1.00 in steps of 0.05.
- A dwell panel with a checkbox for `enabled` and one stepper per dwell option:

| Option | Range | Step |
| --- | --- | --- |
| `delay_ms` | 50 to 2000 ms | 50 |
| `dead_zone_px` | 0 to 50 px | 2 |
| `full_speed_px_s` | 0 to min(200, stop speed - 5) px/s | 5 |
| `stop_speed_px_s` | full speed + 5 to 1000 px/s | 20 |
| `maximum_progress_rate` | 1.00 to 4.00 | 0.25 |
| `indicator_start_progress` | 0 to 1 | 0.05 |
| `direction_reversal_progress_factor` | 0 to 1 | 0.05 |
| `movement_penalty_px` | 1 to 100 px | 1 |
| `distance_curve_full_px` | 10 to 1000 px | 10 |
| `velocity_release_ms` | 10 to 1000 ms | 10 |

Each range contains today's default and stays inside the dwell validation in `config/models.py`. The full speed and stop speed bounds follow each other, so the two can never cross.

Opacity and every dwell option are declared in the root config's `state`, so they survive switching to `social` and back.

### Social Profile

A second profile named `social`, a small keyboard for scrolling a feed:

- Four keys: Up, Down, L, and K.
- A strip with only the profile dropdown, so the user can switch back.
- It reuses the window id `keyboard`, so it opens where the keyboard was.
- Its opacity binds to the same root variable as the default keyboard.
- It has a pointer locator. It has no dwell, hot corners, or lock-screen panel.

Changing the default keyboard updates the expected data in `tests/test_default_profile.py` in the same change.

## Known Risks

- Opening a panel grows a centered layer-shell window, which re-centers it, so keys shift under a dwell pointer while the panel is open. Accepted.
- Theme bindings were not measured. Re-applying a stylesheet live may be slow or flicker.
- Restoring a window's position after a switch is untested on every backend.

## Steps

Each step keeps the full test suite, flake8, and pyright passing.

- [ ] 1. Engine shrink-back after content shrinks.
- [ ] 2. `checkbox`, `stepper`, `dropdown`, and `menu` in `osk.std`.
- [ ] 3. `profile.switch`, `app.profile`, `app.profiles`, position kept across a rebuild, and rollback on a failed switch.
- [ ] 4. Default keyboard strip and the `social` profile, with updated parity data.
- [ ] 5. Document the strip helpers and profile switching in `AGENTS.md`.
