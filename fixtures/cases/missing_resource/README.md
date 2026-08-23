# Case: missing_resource

A scene references a resource (script, texture, sub-resource) whose file no longer
exists or was renamed without updating the reference.

## What a future scanner should detect

- `ext_resource` / `sub_resource` path or id that cannot be resolved at parse time.
- Reference to a `res://` path that does not exist on disk.

## Status

Documentation only. The clean fixture in `fixtures/golden-2d` must never contain this
condition; this directory documents the negative case for Phase 2+ scanner design.
