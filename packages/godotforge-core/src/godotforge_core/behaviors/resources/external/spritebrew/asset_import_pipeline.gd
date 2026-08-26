extends Node
## Asset Import Pipeline for 3D Models
##
## import_fbx() depends on EditorSceneFormatImporterFBX, which is compiled
## only into the Godot editor/tools binary — it does not exist in exported
## (export-template) runtime builds. This script must only be invoked from
## the editor or an editor-context tool script (e.g. `godot --editor
## --script ...`), never from in-game runtime code; is_editor_hint() guards
## make that constraint explicit and fail loudly instead of silently.
## import_gltf() uses GLTFDocument/GLTFState, which are available at
## runtime in exported builds, so it carries no such restriction.

func import_fbx(path: String) -> PackedScene:
    if not Engine.is_editor_hint():
        push_error("import_fbx requires the Godot editor/tools binary (EditorSceneFormatImporterFBX is unavailable in exported builds)")
        return null
    var importer = EditorSceneFormatImporterFBX.new()
    var scene = importer.import_scene(path, EditorSceneFormatImporter.IMPORT_GENERATE_COLLISION_SHAPES)
    return scene

func import_gltf(path: String) -> PackedScene:
    var importer = GLTFDocument.new()
    var state = GLTFState.new()
    var file = FileAccess.open(path, FileAccess.READ)
    var bytes = file.get_buffer(file.get_length())
    importer.append_from_bytes(state, bytes)
    var scene = importer.generate_scene(state)
    return scene
