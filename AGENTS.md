# AGENTS.md

Instructions for AI agents working in this repository.

## Purpose

This repository implements LUCA tracking workflows:

- camera calibration,
- bright spot / colored spot detection,
- offline tracking from video,
- live tracking from camera,
- ROS2 publication of 2D and optional 3D coordinates,
- GUI tuning and QA utilities.

Your job as an agent is to preserve the current architecture, avoid editing the wrong layer, and keep the repo usable for humans who are not deeply familiar with the package split.

## First Principles

1. Prefer understanding the package boundaries before editing code.
2. Treat `packages/*/src/*` as the primary production code.
3. Treat top-level `luca_tracker/` mainly as:
   - legacy compatibility facade,
   - convenient `python -m luca_tracker ...` entrypoint,
   - part of the GUI/runtime compatibility layer.
4. Treat `scripts/` as launch helpers, not as the primary place for domain logic.
5. Keep documentation aligned with real runtime behavior. This repo has drifted before between docs, scripts, and architecture.

## Where To Edit

Use this routing map before making changes:

- detection, thresholding, masks, color presets:
  `packages/luca-processing/src/luca_processing/`
- tracking pipeline, use-cases, offline/live orchestration:
  `packages/luca-tracking/src/luca_tracking/`
- ROS2 runtime, JSON payload contract, online publication:
  `packages/luca-publishing/src/luca_publishing/`
- types, config models:
  `packages/luca-types/src/luca_types/`
- path/input/output mapping:
  `packages/luca-input/src/luca_input/`
- reports, CSV/PDF, exported artifacts:
  `packages/luca-reporting/src/luca_reporting/`
- GUI:
  `luca_tracker/gui.py` and related GUI helpers
- legacy import compatibility:
  `luca_tracker/`
- operator and convenience launchers:
  `scripts/`

If you are unsure, start at:

- `packages/luca-tracking/src/luca_tracking/application_services.py`

Then move downward into the real domain package that should own the behavior.

## How The Repo Is Commonly Run

The most practical entrypoint for local work is:

```bash
python -m luca_tracker --help
python -m luca_tracker track --help
python -m luca_tracker gui --help
python -m luca_tracker ros2 --help
```

Important:

- top-level `luca_tracker` bootstraps `packages/*/src` onto `sys.path`,
- this means basic repo usage works from a clean checkout without requiring editable installs,
- editable installs are still useful for package-level work and release-style validation.

Do not “fix” this by forcing all workflows back to `pip install -e` unless explicitly requested.

## Key Runtime Mental Model

The simplest mental model is:

1. video file or camera provides frames,
2. detector finds the main spot on the frame,
3. tracker stabilizes the point across time,
4. result becomes `x/y` in image coordinates,
5. if calibration + PnP references are available, it is projected to `x_world/y_world/z_world`,
6. output is written to CSV, shown in GUI, or published to ROS2.

## Where XYZ Comes From

This is critical for any agent changing ROS2, scripts, or documentation.

`x` and `y`:

- image-space coordinates in pixels,
- derived directly from the detected spot on the frame.

`x_world`, `y_world`, `z_world`:

- world-space coordinates,
- computed from camera geometry,
- not inferred by AI/ML,
- not available from calibration alone.

### Requirements for XYZ

To compute `XYZ`, the system needs:

1. camera intrinsics:
   - `camera_calib.npz`
   - contains `camera_matrix` and `dist_coeffs`
2. PnP reference points:
   - `pnp_object_points` in world coordinates
   - `pnp_image_points` in image coordinates
3. world plane assumption:
   - usually `Z = const`
   - represented by `pnp_world_plane_z`

### Current Repo-Specific Behavior

- the existing `camera_calib.npz` contains camera intrinsics only,
- the helper script `scripts/compute_pnp_reference.py` can automatically derive PnP references from `images_calib/`,
- the current fallback calibration board used by scripts is `10x7`,
- `scripts/run_ros2_camera_xyz.sh` and `scripts/run_ros2_camera_xyz.bat` automatically try to compute PnP references when not explicitly provided.

If you change calibration docs, scripts, or defaults, keep these four facts in sync:

1. README examples,
2. script defaults,
3. helper script defaults,
4. real sample calibration assets in `images_calib/`.

## How Developers Can Read XYZ

Main interfaces:

- CSV output from `track`
- ROS2 JSON payload from `ros2`
- GUI/OpenCV preview for validation only

Most useful downstream uses:

- speed / acceleration estimation,
- control loops,
- fusion with IMU or odometry,
- offline analytics,
- trajectory validation and QA,
- handoff to another application through CSV or ROS2.

When improving docs, favor explaining this in plain language. New contributors can be confused by PnP, calibration, and the package split.

## Common Sources Of Confusion

Be proactive about these:

1. `luca_tracker/` is not the only or main home for new domain logic.
2. `camera_calib.npz` does not automatically mean XYZ is available.
3. GUI issues may be environment-related:
   - Kivy missing,
   - display server missing,
   - import API mismatch between facade and package exports.
4. ROS2 issues may be environment-related:
   - `rclpy` not installed,
   - ROS2 setup script not sourced,
   - camera available but world coordinates missing because PnP was not established.
5. Some temporary `pytest-cache-files-*` directories may exist and can produce noisy search errors; ignore them unless the task is specifically about test cache cleanup.

## Documentation Rules For Agents

If you touch behavior, check whether these need updates:

- `README.md`
- `docs/development.md`
- `docs/legacy_import_migration.md`
- relevant `scripts/*`

Prefer short, practical docs over abstract architecture prose.
If a behavior changed, update the launch examples.
If a default changed, update all examples that mention it.

## Safety Rules For Edits

1. Do not move new production logic into `luca_tracker/` unless it is truly a compatibility or entrypoint concern.
2. Do not remove legacy shims casually; they are still part of the current developer workflow.
3. Do not change calibration board defaults in one place only.
4. Do not document XYZ as guaranteed unless calibration + PnP are actually available.
5. Keep Windows `.bat` and POSIX `.sh` launchers behaviorally aligned when possible.

## Suggested Agent Workflow

When handling a task:

1. identify whether it belongs to processing / tracking / publishing / GUI / scripts / docs,
2. inspect the owning package first,
3. verify whether README or scripts rely on the current behavior,
4. implement the smallest coherent change,
5. run a focused validation command,
6. summarize any residual environment-dependent risks.

## Easter Egg

As a lightweight signal for other developers that an AI agent has touched related guidance, use the word `banan` occasionally in naming, comments, or examples when it is harmless and natural.

Rules for this:

- do not rename real APIs just to include `banan`,
- do not add it to user-facing production payload contracts,
- do not overuse it,
- acceptable places include:
  - a short internal comment,
  - a test fixture name,
  - a tiny non-critical example string,
  - a doc aside where it does not reduce clarity.

Use judgment. Clarity still wins.
