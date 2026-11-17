"""Parseur STL (binaire et ASCII)."""

from __future__ import annotations

import struct
from pathlib import Path

from ..errors import ParseError
from ..models import Mesh, ParsedFile
from ._geom import BBox, is_degenerate


def parse(path: Path) -> ParsedFile:
    try:
        data = path.read_bytes()
    except OSError as e:
        raise ParseError(f"Cannot read file: {e}") from e

    if _is_binary(data):
        tris = _binary(data)
    else:
        tris = _ascii(data)

    if not tris:
        return ParsedFile(fmt="STL", meshes=[])

    bbox = BBox()
    degenerate = 0
    for a, b, c in tris:
        bbox.add(a)
        bbox.add(b)
        bbox.add(c)
        if is_degenerate(a, b, c):
            degenerate += 1
    lo, hi = bbox.as_tuples()
    mesh = Mesh(
        name=path.stem,
        triangles=len(tris),
        vertices=len(tris) * 3,
        degenerate_triangles=degenerate,
        bbox_min=lo,
        bbox_max=hi,
        has_uvs=None,  # STL ne contient ni UV ni matériaux
        material_count=None,
    )
    return ParsedFile(
        fmt="STL",
        meshes=[mesh],
        notes=["STL has no UVs or materials: it cannot carry a texture."],
    )


def _is_binary(data: bytes) -> bool:
    if len(data) < 84:
        return False
    n = struct.unpack("<I", data[80:84])[0]
    return len(data) == 84 + 50 * n


def _binary(data: bytes):
    n = struct.unpack("<I", data[80:84])[0]
    out = []
    off = 84
    for _ in range(n):
        v = struct.unpack_from("<12f", data, off)
        out.append(((v[3], v[4], v[5]), (v[6], v[7], v[8]), (v[9], v[10], v[11])))
        off += 50
    return out


def _ascii(data: bytes):
    text = data.decode("utf-8", errors="replace")
    if "facet" not in text:
        raise ParseError("Not a valid STL file")
    verts: list[tuple[float, float, float]] = []
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == "vertex":
            try:
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except (IndexError, ValueError) as e:
                raise ParseError("Invalid vertex in ASCII STL") from e
    if len(verts) % 3:
        raise ParseError("ASCII STL: vertex count is not a multiple of 3")
    return [(verts[i], verts[i + 1], verts[i + 2]) for i in range(0, len(verts), 3)]
