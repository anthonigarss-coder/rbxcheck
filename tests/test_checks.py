from builders import (
    CUBE_QUADS, CUBE_TRIS, CUBE_VERTS, fbx_geometry, grid, png_bytes, write_fbx, write_glb,
    write_obj,
)
from rbxcheck import PROFILES, Config, Severity, check_file


def codes(report, severity=None):
    return {i.code for i in report.issues if severity is None or i.severity == severity}


def obj_of(tmp_path, name="Crate", verts=CUBE_VERTS, faces=CUBE_QUADS, **kw):
    return write_obj(tmp_path / "m.obj", [{"name": name, "verts": verts, "faces": faces, **kw}])


def test_clean_cube_has_no_problems(tmp_path):
    r = check_file(obj_of(tmp_path))
    assert r.issues == []
    assert r.errors == r.warnings == 0
    assert r.total_triangles == 12


def test_triangle_limit_boundaries(tmp_path):
    verts, tris = grid(100)  # 20 000 triangles pile
    ok = check_file(write_obj(tmp_path / "a.obj", [{"name": "Floor", "verts": verts, "faces": tris}]))
    assert ok.total_triangles == 20_000
    assert "TRI_LIMIT" not in codes(ok)
    assert "TRI_HIGH" in codes(ok, Severity.WARNING)  # > 10 000 : avertissement

    verts, tris = grid(101)  # 20 402
    bad = check_file(write_obj(tmp_path / "b.obj", [{"name": "Floor", "verts": verts, "faces": tris}]))
    assert "TRI_LIMIT" in codes(bad, Severity.ERROR)


def test_warning_threshold(tmp_path):
    verts, tris = grid(80)  # 12 800
    r = check_file(write_obj(tmp_path / "w.obj", [{"name": "Floor", "verts": verts, "faces": tris}]))
    assert codes(r) == {"TRI_HIGH"}


def test_accessory_profile_is_stricter(tmp_path):
    verts, tris = grid(40)  # 3 200 : ok ; grid(50) = 5 000 : trop
    cfg = Config().with_overrides(profile="accessory")
    assert cfg.profile is PROFILES["accessory"]
    ok = check_file(write_obj(tmp_path / "a.obj", [{"name": "Hat", "verts": verts, "faces": tris}]), cfg)
    assert ok.errors == 0
    verts, tris = grid(50)
    bad = check_file(write_obj(tmp_path / "b.obj", [{"name": "Hat", "verts": verts, "faces": tris}]), cfg)
    assert "TRI_LIMIT" in codes(bad, Severity.ERROR)


def test_custom_limits(tmp_path):
    cfg = Config().with_overrides(max_triangles=10)
    r = check_file(obj_of(tmp_path), cfg)
    assert "TRI_LIMIT" in codes(r, Severity.ERROR)


def test_default_and_duplicate_names(tmp_path):
    r = check_file(obj_of(tmp_path, name="Cube.001"))
    assert "DEFAULT_NAME" in codes(r, Severity.WARNING)

    p = write_obj(tmp_path / "d.obj", [
        {"name": "Wall", "verts": CUBE_VERTS, "faces": CUBE_QUADS},
        {"name": "Wall", "verts": CUBE_VERTS, "faces": CUBE_QUADS},
    ])
    # même nom => l'OBJ fusionne les deux objets : on teste donc les doublons via glTF
    doc_path = write_glb(tmp_path / "dup.glb", CUBE_VERTS, CUBE_TRIS, name="Wall", extra_mesh="Wall")
    assert "DUP_NAME" in codes(check_file(doc_path), Severity.WARNING)
    assert p.exists()


def test_odd_characters_in_name_are_info_only(tmp_path):
    r = check_file(obj_of(tmp_path, name="Épée courte"))
    assert codes(r) == {"NAME_CHARS"}
    assert r.errors == r.warnings == 0


def test_missing_uv_and_multi_material(tmp_path):
    r = check_file(obj_of(tmp_path, uvs=False, materials=["a", "b", "c"]))
    assert {"NO_UV", "MULTI_MATERIAL"} <= codes(r, Severity.WARNING)


def test_degenerate_triangles_warn(tmp_path):
    p = tmp_path / "d.obj"
    p.write_text("o Thing\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\nf 1 1 2\n")
    assert "DEGENERATE" in codes(check_file(p), Severity.WARNING)


def test_scale_checks(tmp_path):
    big = [(x * 5000, y * 5000, z * 5000) for x, y, z in CUBE_VERTS]
    tiny = [(x * 0.001, y * 0.001, z * 0.001) for x, y, z in CUBE_VERTS]
    assert "TOO_BIG" in codes(check_file(obj_of(tmp_path, verts=big)), Severity.WARNING)
    assert "TOO_SMALL" in codes(check_file(obj_of(tmp_path, verts=tiny)), Severity.WARNING)


def test_texture_rules(tmp_path):
    big = check_file(write_glb(tmp_path / "big.glb", CUBE_VERTS, CUBE_TRIS, name="Crate", texture=(5000, 2)))
    assert "TEXTURE_SIZE" in codes(big, Severity.ERROR)
    mid = check_file(write_glb(tmp_path / "mid.glb", CUBE_VERTS, CUBE_TRIS, name="Crate", texture=(2048, 2)))
    assert codes(mid) == {"TEXTURE_BIG"}
    npot = check_file(write_glb(tmp_path / "npot.glb", CUBE_VERTS, CUBE_TRIS, name="Crate", texture=(300, 200)))
    assert codes(npot) == {"TEXTURE_NPOT"}


def test_file_size_limit(tmp_path):
    cfg = Config(max_file_mb=0.0001)
    assert "FILE_SIZE" in codes(check_file(obj_of(tmp_path), cfg), Severity.ERROR)


def test_empty_model(tmp_path):
    p = tmp_path / "e.obj"
    p.write_text("# nothing\n")
    assert "NO_MESH" in codes(check_file(p), Severity.ERROR)


def test_unreadable_and_unsupported(tmp_path):
    assert "READ" in codes(check_file(tmp_path / "ghost.obj"), Severity.ERROR)
    bad = tmp_path / "x.dae"
    bad.write_text("x")
    assert "PARSE" in codes(check_file(bad), Severity.ERROR)


def test_fbx_end_to_end(tmp_path):
    verts, tris = grid(30)  # 1 800 triangles
    p = write_fbx(tmp_path / "f.fbx", [fbx_geometry("Platform", verts, tris, materials=2)])
    r = check_file(p)
    assert r.total_triangles == 1800
    assert codes(r) == {"MULTI_MATERIAL"}


def test_png_helper_is_valid():
    from rbxcheck.parsers.images import image_info

    assert image_info(png_bytes(64, 32)) == ("png", 64, 32)
