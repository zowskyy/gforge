# Case: unresolved_global_class

A script references a `class_name` that is never registered (e.g. the class was renamed
or removed), so `load(...)` or a typed reference fails.

## What a future scanner should detect

- `class_name` references in scripts that have no matching registered global class.
- Duplicate `class_name` declarations across the project.

## Status

Documentation only. Not introduced into the clean fixture.
