import json

from builders import CUBE_QUADS, CUBE_VERTS, grid, write_obj
from rbxcheck.cli import main


def good(tmp_path, name="good.obj"):
    return write_obj(tmp_path / name, [{"name": "Crate", "verts": CUBE_VERTS, "faces": CUBE_QUADS}])


def bad(tmp_path, name="bad.obj"):
    verts, tris = grid(101)
    return write_obj(tmp_path / name, [{"name": "Floor", "verts": verts, "faces": tris}])


def warn_only(tmp_path, name="warn.obj"):
    return write_obj(tmp_path / name, [{"name": "Cube", "verts": CUBE_VERTS, "faces": CUBE_QUADS}])


def test_exit_codes(tmp_path, capsys):
    assert main([str(good(tmp_path))]) == 0
    assert main([str(bad(tmp_path))]) == 1
    assert main([str(tmp_path / "nope.obj")]) == 2


def test_strict_turns_warnings_into_failures(tmp_path):
    f = warn_only(tmp_path)
    assert main([str(f)]) == 0
    assert main(["--strict", str(f)]) == 1


def test_json_output_is_valid(tmp_path, capsys):
    main(["--json", str(good(tmp_path)), str(bad(tmp_path))])
    data = json.loads(capsys.readouterr().out)
    assert [d["errors"] for d in data] == [0, 1]
    assert data[0]["meshes"][0]["name"] == "Crate"
    assert data[1]["issues"][0]["code"] == "TRI_LIMIT"


def test_folder_scan_ignores_other_files(tmp_path, capsys):
    sub = tmp_path / "assets" / "deep"
    sub.mkdir(parents=True)
    good(sub)
    (tmp_path / "assets" / "notes.txt").write_text("hi")
    assert main(["--json", str(tmp_path / "assets")]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_profile_and_overrides(tmp_path):
    f = good(tmp_path)
    assert main(["--max-triangles", "5", str(f)]) == 1
    assert main(["-p", "accessory", str(f)]) == 0


def test_text_output_mentions_verdict(tmp_path, capsys):
    main([str(bad(tmp_path))])
    out = capsys.readouterr().out
    assert "TRI_LIMIT" in out and "FAIL" in out
    main([str(good(tmp_path))])
    assert "OK" in capsys.readouterr().out
