# Case: optional_autoload

An autoload singleton that may or may not be present at runtime (e.g. a debug overlay
enabled only in editor, or an addon that registers itself conditionally).

## What a future scanner should do

- Allow scripts to reference an autoload defensively with `get_node_or_null("/root/X")`
  rather than assuming presence.
- Surface a warning (not an error) when an expected optional autoload is absent.

## Status

Documentation only. `scripts/ui/pause_menu.gd` already demonstrates the defensive
`get_node_or_null("/root/GameState")` pattern against the real autoload.
