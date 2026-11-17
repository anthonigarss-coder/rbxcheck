"""Parseur Wavefront OBJ (géométrie seulement ; .mtl non lu)."""

from __future__ import annotations

from pathlib import Path

from ..errors import ParseError
from ..models import Mesh, ParsedFile
from ._geom import BBox, is_degenerate


class _Obj:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tris = 0
        self.degenerate = 0
        self.used: set[int] = set()
        self.materials: set[str] = set()
        self.has_uv = False
        self.faces = 0
        self.bbox = BBox()


def parse(path: Path) -> ParsedFile:
    positions: list[tuple[float, float, float]] = []
    objects: dict[str, _Obj] = {}
    order: list[_Obj] = []
    current: _Obj | None = None
    pending_material: str | None = None

    def get(name: str) -> _Obj:
        o = objects.get(name)
        if o is None:
            o = _Obj(name)
            objects[name] = o
            order.append(o)
        return o

    try:
        fh = path.open("r", encoding="utf-8", errors="replace")
    except OSError as e:
        raise ParseError(f"Cannot read file: {e}") from e

    with fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line[0] == "#":
                continue
            parts = line.split()
            tag = parts[0]
            if tag == "v":
                try:
                    positions.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except (IndexError, ValueError) as e:
                    raise ParseError(f"Invalid vertex on line {lineno}") from e
            elif tag in ("o", "g"):
                name = " ".join(parts[1:]) or "unnamed"
                current = get(name)
                if pending_material:
                    current.materials.add(pending_material)
            elif tag == "usemtl":
                pending_material = " ".join(parts[1:]) or "default"
                if current is None:
                    current = get(path.stem)
                current.materials.add(pending_material)
            elif tag == "f":
                if current is None:
                    current = get(path.stem)
                    if pending_material:
                        current.materials.add(pending_material)
                idx: list[int] = []
                for token in parts[1:]:
                    fields = token.split("/")
                    try:
                        vi = int(fields[0])
                    except ValueError as e:
                        raise ParseError(f"Invalid face on line {lineno}") from e
                    vi = vi - 1 if vi > 0 else len(positions) + vi
                    if not 0 <= vi < len(positions):
                        raise ParseError(f"Face references a missing vertex (line {lineno})")
                    idx.append(vi)
                    if len(fields) > 1 and fields[1]:
                        current.has_uv = True
                if len(idx) < 3:
                    continue
                current.faces += 1
                current.tris += len(idx) - 2
                for vi in idx:
                    if vi not in current.used:
                        current.used.add(vi)
                        current.bbox.add(positions[vi])
                a = positions[idx[0]]
                for k in range(1, len(idx) - 1):
                    if is_degenerate(a, positions[idx[k]], positions[idx[k + 1]]):
                        current.degenerate += 1

    meshes: list[Mesh] = []
    for o in order:
        if o.faces == 0:
            continue
        lo, hi = o.bbox.as_tuples()
        meshes.append(
            Mesh(
                name=o.name,
                triangles=o.tris,
                vertices=len(o.used),
                degenerate_triangles=o.degenerate,
                bbox_min=lo,
                bbox_max=hi,
                has_uvs=o.has_uv,
                material_count=len(o.materials),
            )
        )
    return ParsedFile(fmt="OBJ", meshes=meshes)
