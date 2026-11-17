import pytest

from builders import (
    CUBE_QUADS, CUBE_TRIS, CUBE_VERTS, fbx_geometry, grid, write_fbx, write_glb,
    write_gltf_embedded, write_obj, write_stl_ascii, write_stl_binary,
)
from rbxcheck.errors import ParseError
from rbxcheck.parsers import parse_file


def cube_obj(tmp_path, **kw):
    return write_obj(tmp_path / "crate.obj", [{"name": "Crate", "verts": CUBE_VERTS, "faces": CUBE_QUADS, **kw}])


# ---------------------------------------------------------------- OBJ
def test_obj_cube(tmp_path):
    r = parse_file(cube_obj(tmp_path))
    (m,) = r.meshes
    assert (m.name, m.triangles, m.vertices) == ("Crate", 12, 8)
    assert m.size == (2, 2, 2)
    assert m.has_uvs is True
    assert m.degenerate_triangles == 0


def test_obj_without_uvs(tmp_path):
    (m,) = parse_file(cube_obj(tmp_path, uvs=False)).meshes
    assert m.has_uvs is False


def test_obj_materials_counted(tmp_path):
    (m,) = parse_file(cube_obj(tmp_path, materials=["wood", "metal"])).meshes
    assert m.material_count == 2


def test_obj_multiple_objects_with_shared_vertex_array(tmp_path):
    p = write_obj(tmp_path / "two.obj", [
        {"name": "A", "verts": CUBE_VERTS, "faces": CUBE_QUADS},
        {"name": "B", "verts": CUBE_VERTS, "faces": CUBE_QUADS[:2]},
    ])
    a, b = parse_file(p).meshes
    assert (a.name, a.triangles) == ("A", 12)
    assert (b.name, b.triangles) == ("B", 4)


def test_obj_negative_indices_and_degenerate(tmp_path):
    p = tmp_path / "neg.obj"
    p.write_text("o T\nv 0 0 0\nv 1 0 0\nv 0 1 0\nv 2 2 2\nf -4 -3 -2\nf 1 1 2\n")
    (m,) = parse_file(p).meshes
    assert m.triangles == 2
    assert m.degenerate_triangles == 1


def test_obj_bad_vertex_reference(tmp_path):
    p = tmp_path / "bad.obj"
    p.write_text("v 0 0 0\nf 1 2 3\n")
    with pytest.raises(ParseError):
        parse_file(p)


# ---------------------------------------------------------------- STL
def test_stl_binary_and_ascii_agree(tmp_path):
    b = parse_file(write_stl_binary(tmp_path / "b.stl", CUBE_VERTS, CUBE_TRIS)).meshes[0]
    a = parse_file(write_stl_ascii(tmp_path / "a.stl", CUBE_VERTS, CUBE_TRIS)).meshes[0]
    assert b.triangles == a.triangles == 12
    assert b.size == a.size == (2, 2, 2)
    assert b.has_uvs is None


def test_stl_garbage_rejected(tmp_path):
    p = tmp_path / "x.stl"
    p.write_text("hello world")
    with pytest.raises(ParseError):
        parse_file(p)


# --------------------------------------------------------------- glTF
@pytest.mark.parametrize("writer,ext,fmt", [(write_gltf_embedded, "gltf", "glTF"), (write_glb, "glb", "GLB")])
def test_gltf_and_glb(tmp_path, writer, ext, fmt):
    r = parse_file(writer(tmp_path / f"c.{ext}", CUBE_VERTS, CUBE_TRIS))
    assert r.fmt == fmt
    (m,) = r.meshes
    assert (m.name, m.triangles, m.vertices) == ("Crate", 12, 8)
    assert m.size == (2, 2, 2)
    assert m.has_uvs is True
    assert m.material_count == 1


def test_glb_texture_dimensions(tmp_path):
    r = parse_file(write_glb(tmp_path / "t.glb", CUBE_VERTS, CUBE_TRIS, texture=(2048, 4)))
    (t,) = r.textures
    assert (t.name, t.width, t.height, t.fmt) == ("albedo", 2048, 4, "png")


def test_gltf_degenerate_detected(tmp_path):
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (5, 5, 5)]
    (m,) = parse_file(write_glb(tmp_path / "d.glb", verts, [(0, 1, 2), (3, 3, 3)])).meshes
    assert m.degenerate_triangles == 1


def test_gltf_without_uv(tmp_path):
    (m,) = parse_file(write_glb(tmp_path / "n.glb", CUBE_VERTS, CUBE_TRIS, uvs=False)).meshes
    assert m.has_uvs is False


def test_gltf_invalid_json(tmp_path):
    p = tmp_path / "bad.gltf"
    p.write_text("{nope")
    with pytest.raises(ParseError):
        parse_file(p)


def test_glb_truncated(tmp_path):
    p = write_glb(tmp_path / "t.glb", CUBE_VERTS, CUBE_TRIS)
    p.write_bytes(p.read_bytes()[:10])
    with pytest.raises(ParseError):
        parse_file(p)


# ---------------------------------------------------------------- FBX
@pytest.mark.parametrize("version", [7400, 7500])
def test_fbx_cube(tmp_path, version):
    p = write_fbx(tmp_path / "c.fbx", [fbx_geometry("Crate", CUBE_VERTS, CUBE_QUADS)], version=version)
    r = parse_file(p)
    assert r.fmt == f"FBX {version}"
    (m,) = r.meshes
    assert (m.name, m.triangles, m.vertices) == ("Crate", 12, 8)
    assert m.size == (2, 2, 2)
    assert m.has_uvs is True
    assert m.material_count == 1


def test_fbx_two_materials_and_texture_name(tmp_path):
    p = write_fbx(
        tmp_path / "m.fbx",
        [fbx_geometry("Crate", CUBE_VERTS, CUBE_QUADS, materials=2)],
        texture_file="wood.png",
    )
    r = parse_file(p)
    assert r.meshes[0].material_count == 2
    assert [t.name for t in r.textures] == ["wood.png"]


def test_fbx_triangle_count_for_grid(tmp_path):
    verts, tris = grid(10)
    p = write_fbx(tmp_path / "g.fbx", [fbx_geometry("Grid", verts, tris)])
    assert parse_file(p).meshes[0].triangles == 200


def test_fbx_ascii_rejected_with_hint(tmp_path):
    p = tmp_path / "a.fbx"
    p.write_text("; FBX 7.4.0 project file\nFBXHeaderExtension: {}\n")
    with pytest.raises(ParseError, match="binary"):
        parse_file(p)


def test_fbx_truncated(tmp_path):
    p = write_fbx(tmp_path / "c.fbx", [fbx_geometry("Crate", CUBE_VERTS, CUBE_QUADS)])
    p.write_bytes(p.read_bytes()[:120])
    with pytest.raises(ParseError):
        parse_file(p)


def test_unknown_extension(tmp_path):
    p = tmp_path / "x.dae"
    p.write_text("x")
    with pytest.raises(ParseError, match="Unsupported"):
        parse_file(p)


def test_fbx_mesh_takes_object_name_not_mesh_data_name(tmp_path):
    # Blender : objet "Crate", donnée de maillage "Cube"
    p = write_fbx(
        tmp_path / "n.fbx",
        [fbx_geometry("Cube", CUBE_VERTS, CUBE_QUADS, geom_id=42)],
        object_names={42: "Crate"},
    )
    assert parse_file(p).meshes[0].name == "Crate"
