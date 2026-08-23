# Case: circular_preload

Two scripts `preload` each other (directly or transitively), which can cause
initialization-order errors depending on when the scripts are first referenced.

## What a future scanner should detect

- Cycles in the static `preload` dependency graph across script files.

## Status

Documentation only. Not introduced into the clean fixture. The clean fixture uses
`load` (runtime) rather than `preload` for dynamic targets to stay cycle-free.
