# Hub Plan Cache API

Plan computation cache (Slice 4G). Checked before planning; stored after successful plan. Cache key includes project_root_hash for automatic invalidation.

---

## Cache Key

The cache key is a tuple of three components:
- `goal_path`: Relative path to the goal file (e.g., "mygame.yaml")
- `goal_hash`: SHA-256 hash of the compiled goal (from `GoalCompilation.goal_hash`)
- `project_root_hash`: SHA-256 hash of the project root directory contents

```python
cache_key = (goal_path, goal_hash, project_root_hash)
```

The `project_root_hash` ensures automatic cache invalidation when any project file changes, without requiring explicit cache management.

---

## Functions

### `get_cached_plan(root: Path, goal_path: str, goal_hash: str) -> CreatorPatch | None`

Look up a cached plan. Returns the cached `CreatorPatch` if found, `None` otherwise. Read-only operation; never writes.

**Parameters:**
- `root`: Project root path
- `goal_path`: Relative goal file path (e.g., "mygame.yaml")
- `goal_hash`: Goal content hash from compilation

**Returns:** `CreatorPatch` or `None`

**Example:**
```python
from godotforge_core.hub.cache import get_cached_plan
from godotforge_core.hub.goal import compile_goal
from pathlib import Path

compilation = compile_goal(goal_data)
if compilation.status == "ok":
    cached = get_cached_plan(Path("."), "mygame.yaml", compilation.goal_hash)
    if cached:
        print("Cache hit!")
        patch = cached
    else:
        print("Cache miss - planning...")
```

---

### `store_plan(root: Path, goal_path: str, goal_hash: str, project_root_hash: str, patch: CreatorPatch) -> None`

Store a plan in the cache after successful planning. The cache entry is keyed by `(goal_path, goal_hash, project_root_hash)`.

**Parameters:**
- `root`: Project root path
- `goal_path`: Relative goal file path
- `goal_hash`: Goal content hash
- `project_root_hash`: Project root hash (from `_compute_project_root_hash`)
- `patch`: CreatorPatch to cache

**Example:**
```python
from godotforge_core.hub.cache import store_plan, _compute_project_root_hash
from godotforge_core.creator.plan import plan_creator_manifest
from pathlib import Path

patch = plan_creator_manifest(Path("."), manifest_dict)
project_root_hash = _compute_project_root_hash(Path("."))
store_plan(Path("."), "mygame.yaml", compilation.goal_hash, project_root_hash, patch)
```

---

### `_compute_project_root_hash(root: Path) -> str`

Compute SHA-256 hash of the project root directory contents. Used as part of the cache key for automatic invalidation.

Hashes all files under the project root (excluding `.godotforge/` metadata directory) in deterministic sorted order.

**Parameters:**
- `root`: Project root path

**Returns:** 64-character lowercase hex SHA-256 hash

---

## Cache Behavior

### TTL: None

The cache has no time-to-live expiration. Entries are invalidated **only** when the `project_root_hash` changes, which happens when any project file is added, removed, or modified. This provides automatic, correct cache invalidation without manual intervention.

### Storage Location

Cache entries are stored under `.godotforge/hub/plan-cache/` as individual JSON files named by the hash of the cache key.

### Concurrency

Cache operations are thread-safe. Multiple concurrent readers are supported. Writers use atomic temp-file + replace pattern consistent with other Hub stores.

### Cache Miss Handling

On cache miss, the orchestrator proceeds with normal planning via `plan_creator_manifest`. After successful planning, the result is stored for future use.

### Cache Invalidation Scenarios

| Scenario | Cache Valid? |
|----------|--------------|
| Goal file unchanged, project files unchanged | ✅ Yes |
| Goal file modified | ❌ No (goal_hash changes) |
| Project source file modified | ❌ No (project_root_hash changes) |
| New file added to project | ❌ No (project_root_hash changes) |
| File deleted from project | ❌ No (project_root_hash changes) |
| `.godotforge/` metadata changed | ✅ Yes (excluded from hash) |
| Godot engine version changed | ✅ Yes (not in project_root_hash) |

---

## Usage in Orchestrator

Both `preview_goal` and `run_goal` use the cache:

```python
# In preview_goal (read-only cache lookup)
cached_patch = get_cached_plan(root, goal_path, compilation.goal_hash)
if cached_patch is not None:
    patch = cached_patch
else:
    patch = plan_creator_manifest(root, manifest_dict)

# In run_goal (cache lookup + store on miss)
cached_patch = get_cached_plan(root, goal_path, compilation.goal_hash)
if cached_patch is not None:
    patch = cached_patch
else:
    patch = plan_creator_manifest(root, manifest_dict)
    project_root_hash = _compute_project_root_hash(root)
    store_plan(root, goal_path, compilation.goal_hash, project_root_hash, patch)
```

---

## Manual Cache Management

To clear the cache manually:
```bash
rm -rf .godotforge/hub/plan-cache/
```

Or programmatically:
```python
import shutil
from pathlib import Path

cache_dir = Path(".godotforge/hub/plan-cache")
if cache_dir.exists():
    shutil.rmtree(cache_dir)
```