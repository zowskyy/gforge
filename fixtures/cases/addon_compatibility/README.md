# Case: addon_compatibility

A third-party addon is present in `addons/` but targets a different Godot minor version
or expects APIs the current engine build does not provide.

## What a future scanner should do

- Read each addon's declared `plugin.cfg` engine compatibility version.
- Warn when an addon's supported version range excludes the resolved engine version.

## Status

Documentation only. No addon is shipped in the clean fixture yet; this case defines the
future detection requirement for Phase 2+ addon auditing.
