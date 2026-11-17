"""Générateurs de fichiers 3D minimaux, utilisés uniquement par les tests."""

from __future__ import annotations

import array
import base64
import json
import struct
import zlib
from pathlib import Path

CUBE_VERTS = [
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
]
CUBE_QUADS = [
    (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
    (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3),
]
CUBE_TRIS = [(q[0], q[1], q[2]) for q in CUBE_QUADS] + [(q[0], q[2], q[3]) for q in CUBE_QUADS]


def grid(n: int, size: float = 1.0):
    """Grille n x n quads => 2*n*n triangles (sommets distincts, donc pas dégénérés)."""
    verts = [(x * size / n, y * size / n, 0.0) for y in range(n + 1) for x in range(n + 1)]
    tris = []
    for y in range(n):
        for x in range(n):
            a = y * (n + 1) + x
            b = a + 1
            c = a + (n + 1)
            d = c + 1
            tris += [(a, b, d), (a, d, c)]
    return verts, tris


# ------------------------------------------------------------------- OBJ


def write_obj(path: Path, objects: list[dict]) -> Path:
    """objects: [{name, verts, faces, uvs(bool), materials(list)}] ; faces = tuples d'indices (0-based)."""
    lines = []
    offset = 0
    for o in objects:
        lines.append(f"o {o['name']}")
        for v in o["verts"]:
            lines.append("v %f %f %f" % v)
        if o.get("uvs", True):
            lines.append("vt 0 0")
        mats = o.get("materials") or []
        for k, face in enumerate(o["faces"]):
            if mats:
                lines.append(f"usemtl {mats[k % len(mats)]}")
            if o.get("uvs", True):
                lines.append("f " + " ".join(f"{i + 1 + offset}/1" for i in face))
            else:
                lines.append("f " + " ".join(f"{i + 1 + offset}" for i in face))
        offset += len(o["verts"])
    path.write_text("\n".join(lines) + "\n")
    return path


# ------------------------------------------------------------------- STL


def write_stl_binary(path: Path, verts, tris) -> Path:
    out = bytearray(b"\0" * 80)
    out += struct.pack("<I", len(tris))
    for a, b, c in tris:
        out += struct.pack("<12f", 0, 0, 1, *verts[a], *verts[b], *verts[c])
        out += b"\0\0"
    path.write_bytes(bytes(out))
    return path


def write_stl_ascii(path: Path, verts, tris) -> Path:
    lines = ["solid test"]
    for a, b, c in tris:
        lines.append("facet normal 0 0 1\n outer loop")
        for i in (a, b, c):
            lines.append("  vertex %f %f %f" % verts[i])
        lines.append(" endloop\nendfacet")
    lines.append("endsolid test")
    path.write_text("\n".join(lines))
    return path


# ------------------------------------------------------------------ glTF


def png_bytes(width: int, height: int) -> bytes:
    """PNG valide minimal (gris 8 bits)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = b"".join(b"\0" + b"\x80" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def gltf_document(verts, tris, name="Crate", uvs=True, materials=1, texture=None, extra_mesh=None):
    """Renvoie (json_dict, binaire). `texture` = (w, h) pour embarquer un PNG."""
    pos = b"".join(struct.pack("<3f", *v) for v in verts)
    idx = b"".join(struct.pack("<3H", *t) for t in tris)
    uv = b"".join(struct.pack("<2f", 0.0, 0.0) for _ in verts)

    blob = bytearray()
    views, accessors = [], []

    def add_view(data: bytes, target=None) -> int:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        return len(views) - 1

    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    accessors.append({"bufferView": add_view(pos), "componentType": 5126, "count": len(verts), "type": "VEC3", "min": lo, "max": hi})
    accessors.append({"bufferView": add_view(idx), "componentType": 5123, "count": len(tris) * 3, "type": "SCALAR"})
    attrs = {"POSITION": 0}
    if uvs:
        accessors.append({"bufferView": add_view(uv), "componentType": 5126, "count": len(verts), "type": "VEC2"})
        attrs["TEXCOORD_0"] = 2

    prims = []
    per = max(1, len(tris) // max(materials, 1))
    for m in range(materials):
        # un seul primitive suffit pour les tests : on duplique les références
        prims.append({"attributes": attrs, "indices": 1, "material": m})
    doc = {
        "asset": {"version": "2.0"},
        "meshes": [{"name": name, "primitives": prims}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": 0}],
    }
    if extra_mesh:
        doc["meshes"].append({"name": extra_mesh, "primitives": [{"attributes": attrs, "indices": 1}]})
    if texture:
        img = png_bytes(*texture)
        doc["images"] = [{"name": "albedo", "bufferView": add_view(img)}]
    doc["bufferViews"] = views
    doc["buffers"] = [{"byteLength": len(blob)}]
    return doc, bytes(blob)


def write_gltf_embedded(path: Path, *args, **kwargs) -> Path:
    doc, blob = gltf_document(*args, **kwargs)
    doc["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(blob).decode()
    path.write_text(json.dumps(doc))
    return path


def write_glb(path: Path, *args, **kwargs) -> Path:
    doc, blob = gltf_document(*args, **kwargs)
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + blob
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    return path


# ------------------------------------------------------------------- FBX


def _prop(p) -> bytes:
    t, v = p
    if t == "S":
        raw = v.encode()
        return b"S" + struct.pack("<I", len(raw)) + raw
    if t == "L":
        return b"L" + struct.pack("<q", v)
    if t == "I":
        return b"I" + struct.pack("<i", v)
    if t == "D":
        return b"D" + struct.pack("<d", v)
    if t in ("d", "i"):
        code = {"d": "d", "i": "i"}[t]
        data = array.array(code, v).tobytes()
        comp = zlib.compress(data)
        return t.encode() + struct.pack("<III", len(v), 1, len(comp)) + comp
    raise ValueError(t)


def _node(name: str, props, children, pos: int, wide: bool) -> bytes:
    header = 25 if wide else 13
    pbytes = b"".join(_prop(p) for p in props)
    nm = name.encode()
    body_start = pos + header + len(nm) + len(pbytes)
    kids = b""
    cur = body_start
    for c in children:
        cb = _node(*c, pos=cur, wide=wide)
        kids += cb
        cur += len(cb)
    if children:
        kids += b"\0" * header
    end = pos + header + len(nm) + len(pbytes) + len(kids)
    fmt = "<QQQB" if wide else "<IIIB"
    return struct.pack(fmt, end, len(props), len(pbytes), len(nm)) + nm + pbytes + kids


def fbx_geometry(name, verts, faces, uvs=True, materials=1, geom_id=1):
    flat = [c for v in verts for c in v]
    poly = []
    for f in faces:
        poly += list(f[:-1]) + [~f[-1]]
    kids = [
        ("Vertices", [("d", flat)], []),
        ("PolygonVertexIndex", [("i", poly)], []),
    ]
    if uvs:
        kids.append(("LayerElementUV", [("I", 0)], []))
    if materials:
        mats = [i % materials for i in range(len(faces))]
        kids.append(("LayerElementMaterial", [("I", 0)], [
            ("MappingInformationType", [("S", "ByPolygon" if materials > 1 else "AllSame")], []),
            ("Materials", [("i", mats)], []),
        ]))
    return ("Geometry", [("L", geom_id), ("S", f"{name}\x00\x01Geometry"), ("S", "Mesh")], kids)


def write_fbx(path: Path, geometries: list, version: int = 7400, texture_file: str | None = None,
              object_names: dict[int, str] | None = None) -> Path:
    """object_names : {id_geometry: nom_objet} => ajoute des Model + Connections comme Blender."""
    wide = version >= 7500
    objects = list(geometries)
    connections = []
    for k, (geom_id, obj_name) in enumerate((object_names or {}).items()):
        model_id = 1000 + k
        objects.append(("Model", [("L", model_id), ("S", f"{obj_name}\x00\x01Model"), ("S", "Mesh")], []))
        connections.append(("C", [("S", "OO"), ("L", geom_id), ("L", model_id)], []))
    if texture_file:
        objects.append(("Texture", [("L", 9), ("S", "Tex\x00\x01Texture"), ("S", "")], [
            ("FileName", [("S", "C:\\art\\" + texture_file)], []),
        ]))
    roots = [("Objects", [], objects)]
    if connections:
        roots.append(("Connections", [], connections))
    out = bytearray(b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", version))
    for r in roots:
        out += _node(*r, pos=len(out), wide=wide)
    out += b"\0" * (25 if wide else 13)
    out += b"\0" * 16  # pied de page factice
    path.write_bytes(bytes(out))
    return path
