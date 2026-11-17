# rbxcheck

Check your 3D models **before** you import them into Roblox Studio.

`rbxcheck` reads OBJ, STL, glTF/GLB and (binary) FBX files and tells you about the
problems that usually make an import fail or look wrong: too many triangles, several
materials on one mesh, missing UVs, huge textures, wrong scale, default Blender names...

- Pure Python 3.12+, **no dependencies**
- Works from a terminal, in scripts and in CI (exit codes + JSON output)
- Read-only: it never modifies your files

English | [Français](README.fr.md)

## Install

With [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/anthonigarss-coder/rbxcheck
cd rbxcheck
uv tool install .      # installs the `rbxcheck` command
```

Or run it without installing: `uv run rbxcheck model.fbx`.

## Usage

```bash
rbxcheck crate.fbx                 # one file
rbxcheck assets/                   # every model in a folder (recursive)
rbxcheck -p accessory hat.glb      # stricter budget for UGC accessories
rbxcheck --strict *.obj            # warnings count as failures
rbxcheck --json crate.fbx          # machine-readable output
```

Example output:

```text
scene.fbx
  format: FBX 7400   size: 50.5 KB   triangles: 1,292   meshes: 2
    - Crate: 12 tris, 8 verts   size: 2 x 2 x 2
    - Icosphere: 1,280 tris, 642 verts   size: 3 x 3 x 3

  WARNING MULTI_MATERIAL [Crate] 2 materials on one mesh. Studio applies a single texture per MeshPart: merge materials or split the mesh.
  WARNING NO_UV          [Icosphere] No UV map: textures cannot be applied.
  WARNING DEFAULT_NAME   [Icosphere] 'Icosphere' looks like a default name. Give it a meaningful name.

OK  (0 error(s), 3 warning(s))
```

### Options

| Option | Meaning |
| --- | --- |
| `-p`, `--profile` | `mesh` (default: hard cap 20,000 triangles, warning above 10,000) or `accessory` (hard cap 4,000) |
| `--max-triangles N` | override the hard limit |
| `--warn-triangles N` | override the warning threshold |
| `--strict` | treat warnings as failures |
| `--json` | print a JSON report |
| `--no-color` | disable colors (`NO_COLOR` is also respected) |

Exit codes: `0` everything fine, `1` at least one file failed, `2` usage error.

## What is checked

| Code | Level | Meaning |
| --- | --- | --- |
| `TRI_LIMIT` | error | more triangles than the profile allows |
| `TRI_HIGH` | warning | above the comfortable budget |
| `TEXTURE_SIZE` | error | texture larger than 4096 px (glTF/GLB embedded or external images) |
| `FILE_SIZE` | error | file larger than ~20 MB |
| `NO_MESH`, `PARSE`, `READ` | error | empty, unreadable or unsupported file |
| `MULTI_MATERIAL` | warning | several materials on one mesh (Studio applies one texture per MeshPart) |
| `NO_UV` | warning | no UV map, so no texture possible |
| `DEGENERATE` | warning | zero-area triangles |
| `TOO_BIG` / `TOO_SMALL` | warning | suspicious dimensions, usually a scale problem |
| `DEFAULT_NAME`, `DUP_NAME` | warning | names like `Cube.001`, or the same name used twice |
| `TEXTURE_BIG`, `TEXTURE_NPOT`, `NAME_CHARS`, `NOTE` | info | nice-to-know hints |

## Format support

| Format | Triangles | Size | UVs | Materials | Textures |
| --- | :-: | :-: | :-: | :-: | :-: |
| OBJ | yes | yes | yes | yes (`usemtl`) | no (`.mtl` not read) |
| STL (binary + ASCII) | yes | yes | n/a | n/a | n/a |
| glTF / GLB | yes | yes (accessor bounds) | yes | yes | yes (PNG/JPEG dimensions) |
| FBX (binary) | yes | yes | yes | yes | names only |

ASCII FBX files are not supported: export as binary FBX (Blender's default).
In FBX, each mesh is reported under the name of its **object**, which is what Roblox uses.

## Good to know

- **Limits change.** Roblox's published numbers are not identical everywhere (about 20k–21k
  triangles per mesh, 10k for some import paths, 4k for rigid accessories). They are only
  defaults here: use `--max-triangles` / `--warn-triangles` to match what Roblox currently says.
- Sizes are in the file's own units, measured on the mesh before any node transform.
  Check that your exporter scale matches what you expect in studs.
- For glTF, each mesh *definition* is counted once, even if several nodes reuse it.

## Use it as a library

```python
from rbxcheck import Config, check_file

report = check_file("crate.fbx", Config().with_overrides(profile="accessory"))
print(report.total_triangles, report.errors, report.warnings)
for issue in report.issues:
    print(issue.severity.name, issue.code, issue.message)
```

## Development

```bash
uv run pytest
```

The tests generate their own tiny OBJ/STL/glTF/FBX files, so no assets are stored in the
repository. Parsers were also cross-checked against files exported by Blender and trimesh.

## License

MIT
