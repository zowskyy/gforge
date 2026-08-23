# Case: dynamic_load

A script loads a resource at runtime via `load(path)` or `preload(variable)` where the
target path is computed from runtime state and is therefore unknown at parse time.

This is a **supported pattern**, not a defect. The clean fixture exercises it in
`scripts/systems/resource_catalog.gd` and `scripts/systems/scene_router.gd`.

## What a future scanner should do

- Recognize dynamic-load patterns and avoid false "missing resource" reports.
- Treat the computed base path as a load root and validate only its existence if
  determinable.

## Status

Documentation only. The clean fixture intentionally includes dynamic loading.
