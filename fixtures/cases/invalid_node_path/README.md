# Case: invalid_node_path

A script uses `get_node("path")` or `get_node_or_null("path")` that does not match the
actual node tree, producing a null reference at runtime instead of a parse error.

## What a future scanner should detect

- `$NodePath` or `get_node(...)` references that cannot be statically resolved against
  the associated scene tree.

## Status

Documentation only. Not introduced into the clean fixture.
