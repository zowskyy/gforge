"""Project scanner core (framework-neutral, no Click).

PROJECT-0001 introduces only the file-inventory primitive. PROJECT-0002 adds
project-settings parsing. Graph persistence and GDScript/TSCN deep parsing
arrive in later slices.
"""

from .gdscript import (
    ScriptDependency,
    ScriptModel,
    index_scripts,
    parse_script,
    script_dependency_paths,
)
from .inventory import inventory_project
from .model import InventoryResult
from .paths import exists, filesystem_path, res_path
from .project_godot import (
    Autoload,
    InputAction,
    ProjectSettings,
    parse_export_preset_names,
    parse_project_settings,
)
from .tscn import (
    ExtResourceRef,
    NodeRef,
    SceneModel,
    SubResourceRef,
    index_scenes,
    parse_scene,
    scene_dependencies,
)

# ``build_scan_report`` is intentionally not imported here to avoid a
# circular init (scan.__init__ -> report -> graph -> scan). Import it
# directly via ``godotforge_core.scan.report`` when needed.
__all__ = [
    "inventory_project",
    "InventoryResult",
    "Autoload",
    "InputAction",
    "ProjectSettings",
    "parse_project_settings",
    "parse_export_preset_names",
    "ExtResourceRef",
    "NodeRef",
    "SceneModel",
    "SubResourceRef",
    "index_scenes",
    "parse_scene",
    "scene_dependencies",
    "ScriptDependency",
    "ScriptModel",
    "index_scripts",
    "parse_script",
    "script_dependency_paths",
    "exists",
    "filesystem_path",
    "res_path",
]
