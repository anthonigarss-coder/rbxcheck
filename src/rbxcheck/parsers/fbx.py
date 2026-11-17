"""Parseur FBX binaire (le format par défaut de Blender et de l'exporteur Roblox).

Seules les infos utiles à la validation sont décodées : sommets, indices de
polygones, présence d'UV, matériaux, noms des textures. Les FBX ASCII ne sont
pas gérés (ré-exporte en binaire).
"""

from __future__ import annotations

import array
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import ParseError
from ..models import Mesh, ParsedFile, Texture
from ._geom import BBox, is_degenerate

MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
_WANTED_ARRAYS = {"Vertices", "PolygonVertexIndex", "Materials"}
_ARRAY_CODES = {"f": ("f", 4), "d": ("d", 8), "l": ("q", 8), "i": ("i", 4), "b": ("b", 1)}


@dataclass
class _Node:
    name: str
    props: list = field(default_factory=list)
    children: list["_Node"] = field(default_factory=list)

    def child(self, name: str) -> "_Node | None":
        for c in self.children:
            if c.name == name:
                return c
        return None


def parse(path: Path) -> ParsedFile:
    try:
        data = path.read_bytes()
    except OSError as e:
        raise ParseError(f"Cannot read file: {e}") from e

    if data[:18] == b"; FBX" or data.lstrip()[:1] == b";":
        raise ParseError("ASCII FBX is not supported. Re-export as binary FBX.")
    if not data.startswith(MAGIC):
        raise ParseError("Not a binary FBX file (bad header)")

    try:
        version = struct.unpack_from("<I", data, 23)[0]
        roots = _read_nodes(data, 27, len(data), version >= 7500)
    except (struct.error, zlib.error, IndexError, ValueError) as e:
        raise ParseError(f"Corrupted or truncated FBX file ({e})") from e

    objects = next((n for n in roots if n.name == "Objects"), None)
    if objects is None:
        raise ParseError("FBX file has no 'Objects' section")

    object_names = _geometry_object_names(roots, objects)

    meshes: list[Mesh] = []
    textures: list[Texture] = []
    for node in objects.children:
        if node.name == "Geometry" and len(node.props) >= 3 and node.props[2] == "Mesh":
            mesh = _mesh(node, len(meshes))
            # Roblox nomme le MeshPart d'après l'objet (Model), pas la donnée de maillage.
            mesh.name = object_names.get(node.props[0], mesh.name)
            meshes.append(mesh)
        elif node.name == "Texture":
            tex = node.child("RelativeFilename") or node.child("FileName")
            if tex and tex.props and isinstance(tex.props[0], str) and tex.props[0]:
                fname = tex.props[0].replace("\\", "/").rsplit("/", 1)[-1]
                textures.append(Texture(name=fname))
    return ParsedFile(fmt=f"FBX {version}", meshes=meshes, textures=textures)


# ------------------------------------------------------------------ lecture


def _read_nodes(data: bytes, pos: int, end: int, wide: bool) -> list[_Node]:
    header = 25 if wide else 13
    fmt = "<QQQB" if wide else "<IIIB"
    nodes: list[_Node] = []
    while pos + header <= end:
        end_offset, n_props, props_len, name_len = struct.unpack_from(fmt, data, pos)
        if end_offset == 0:  # enregistrement nul = fin de la liste
            break
        if end_offset > len(data):
            raise ValueError("node offset out of range")
        name = data[pos + header : pos + header + name_len].decode("ascii", "replace")
        props_start = pos + header + name_len
        props_end = props_start + props_len
        props = _read_props(data, props_start, n_props, name in _WANTED_ARRAYS)
        children = _read_nodes(data, props_end, end_offset, wide) if props_end < end_offset else []
        nodes.append(_Node(name, props, children))
        pos = end_offset
    return nodes


def _read_props(data: bytes, pos: int, count: int, want_arrays: bool) -> list:
    out: list = []
    for _ in range(count):
        t = chr(data[pos])
        pos += 1
        if t == "Y":
            out.append(struct.unpack_from("<h", data, pos)[0]); pos += 2
        elif t == "C":
            out.append(bool(data[pos])); pos += 1
        elif t == "I":
            out.append(struct.unpack_from("<i", data, pos)[0]); pos += 4
        elif t == "F":
            out.append(struct.unpack_from("<f", data, pos)[0]); pos += 4
        elif t == "D":
            out.append(struct.unpack_from("<d", data, pos)[0]); pos += 8
        elif t == "L":
            out.append(struct.unpack_from("<q", data, pos)[0]); pos += 8
        elif t in _ARRAY_CODES:
            n, enc, clen = struct.unpack_from("<III", data, pos)
            pos += 12
            if want_arrays:
                code, size = _ARRAY_CODES[t]
                chunk = data[pos : pos + clen]
                if enc == 1:
                    chunk = zlib.decompress(chunk)
                arr = array.array(code)
                arr.frombytes(chunk[: n * size])
                if sys.byteorder == "big":
                    arr.byteswap()
                out.append(arr)
            else:
                out.append(None)
            pos += clen
        elif t == "S" or t == "R":
            n = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            raw = data[pos : pos + n]
            pos += n
            out.append(raw.decode("utf-8", "replace") if t == "S" else raw)
        else:
            raise ValueError(f"unknown property type {t!r}")
    return out


# --------------------------------------------------------------- géométrie


def _geometry_object_names(roots: list[_Node], objects: _Node) -> dict[int, str]:
    """Associe l'id de chaque Geometry au nom de l'objet (Model) qui l'utilise."""
    models: dict[int, str] = {}
    for n in objects.children:
        if n.name == "Model" and len(n.props) >= 2 and isinstance(n.props[1], str):
            name = n.props[1].split("\x00")[0].strip()
            if name:
                models[n.props[0]] = name
    result: dict[int, str] = {}
    conns = next((n for n in roots if n.name == "Connections"), None)
    if conns:
        for c in conns.children:
            # C: "OO", enfant, parent
            if c.name == "C" and len(c.props) >= 3 and c.props[0] == "OO":
                child, parent = c.props[1], c.props[2]
                if parent in models and child not in result:
                    result[child] = models[parent]
    return result


def _clean_name(raw: str, index: int) -> str:
    # Les noms FBX ressemblent à "Cube\x00\x01Geometry"
    name = raw.split("\x00")[0].strip()
    return name or f"geometry_{index}"


def _mesh(node: _Node, index: int) -> Mesh:
    name = _clean_name(node.props[1] if isinstance(node.props[1], str) else "", index)
    verts_node = node.child("Vertices")
    poly_node = node.child("PolygonVertexIndex")
    flat = verts_node.props[0] if verts_node and verts_node.props else array.array("d")
    polys = poly_node.props[0] if poly_node and poly_node.props else array.array("i")

    points = [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat) - 2, 3)]
    bbox = BBox()
    for p in points:
        bbox.add(p)

    tris = 0
    degenerate = 0
    poly: list[int] = []
    for raw in polys:
        end_of_poly = raw < 0
        idx = ~raw if end_of_poly else raw
        poly.append(idx)
        if end_of_poly:
            if len(poly) >= 3:
                tris += len(poly) - 2
                try:
                    a = points[poly[0]]
                    for k in range(1, len(poly) - 1):
                        if is_degenerate(a, points[poly[k]], points[poly[k + 1]]):
                            degenerate += 1
                except IndexError:
                    pass
            poly = []

    lo, hi = bbox.as_tuples()
    return Mesh(
        name=name,
        triangles=tris,
        vertices=len(points),
        degenerate_triangles=degenerate,
        bbox_min=lo,
        bbox_max=hi,
        has_uvs=node.child("LayerElementUV") is not None,
        material_count=_material_count(node),
    )


def _material_count(node: _Node) -> int | None:
    layer = node.child("LayerElementMaterial")
    if layer is None:
        return 0
    mapping = layer.child("MappingInformationType")
    if mapping and mapping.props and mapping.props[0] == "AllSame":
        return 1
    mats = layer.child("Materials")
    if mats and mats.props and mats.props[0] is not None:
        return len(set(mats.props[0])) or 1
    return None
