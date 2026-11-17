"""Parseur glTF 2.0 (.gltf avec buffers externes ou embarqués, et .glb)."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path
from urllib.parse import unquote

from ..errors import ParseError
from ..models import Mesh, ParsedFile, Texture
from ._geom import BBox, is_degenerate
from .images import image_info

_COMPONENT = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
_TYPE_SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}

GLB_MAGIC = 0x46546C67  # "glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


def parse(path: Path) -> ParsedFile:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise ParseError(f"Cannot read file: {e}") from e

    glb_bin: bytes | None = None
    if raw[:4] == b"glTF":
        doc, glb_bin = _read_glb(raw)
        fmt = "GLB"
    else:
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ParseError(f"Invalid glTF JSON: {e}") from e
        fmt = "glTF"

    if not isinstance(doc, dict) or "asset" not in doc:
        raise ParseError("Not a glTF 2.0 file (missing 'asset')")

    notes: list[str] = []
    buffers = _load_buffers(doc, path.parent, glb_bin, notes)
    meshes = [_mesh(doc, buffers, i, m) for i, m in enumerate(doc.get("meshes", []))]
    textures = _textures(doc, buffers, path.parent)
    return ParsedFile(fmt=fmt, meshes=meshes, textures=textures, notes=notes)


# --------------------------------------------------------------------- GLB


def _read_glb(raw: bytes) -> tuple[dict, bytes | None]:
    if len(raw) < 20:
        raise ParseError("GLB file is truncated")
    magic, version, length = struct.unpack_from("<III", raw, 0)
    if magic != GLB_MAGIC:
        raise ParseError("Invalid GLB header")
    if version != 2:
        raise ParseError(f"Unsupported GLB version {version} (only 2.0)")
    pos = 12
    doc = None
    bin_chunk = None
    end = min(length, len(raw))
    while pos + 8 <= end:
        clen, ctype = struct.unpack_from("<II", raw, pos)
        data = raw[pos + 8 : pos + 8 + clen]
        if ctype == CHUNK_JSON and doc is None:
            try:
                doc = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise ParseError(f"Invalid JSON chunk in GLB: {e}") from e
        elif ctype == CHUNK_BIN and bin_chunk is None:
            bin_chunk = bytes(data)
        pos += 8 + clen + (-clen % 4)
    if doc is None:
        raise ParseError("GLB has no JSON chunk")
    return doc, bin_chunk


# ----------------------------------------------------------------- buffers


def _load_buffers(doc: dict, base: Path, glb_bin: bytes | None, notes: list[str]) -> list[bytes | None]:
    out: list[bytes | None] = []
    for i, buf in enumerate(doc.get("buffers", [])):
        uri = buf.get("uri")
        if uri is None:
            out.append(glb_bin)
        elif uri.startswith("data:"):
            try:
                out.append(base64.b64decode(uri.split(",", 1)[1]))
            except Exception:
                out.append(None)
                notes.append(f"Buffer {i}: invalid embedded data.")
        else:
            f = base / unquote(uri)
            try:
                out.append(f.read_bytes())
            except OSError:
                out.append(None)
                notes.append(f"Buffer {i}: external file '{uri}' not found, some checks skipped.")
    return out


def _view_bytes(doc: dict, buffers: list[bytes | None], view_idx: int) -> tuple[bytes, int, int | None] | None:
    views = doc.get("bufferViews", [])
    if not 0 <= view_idx < len(views):
        return None
    v = views[view_idx]
    buf = buffers[v.get("buffer", 0)] if v.get("buffer", 0) < len(buffers) else None
    if buf is None:
        return None
    start = v.get("byteOffset", 0)
    return buf, start, v.get("byteStride")


def _read_accessor(doc: dict, buffers: list[bytes | None], idx: int) -> list[tuple] | None:
    accessors = doc.get("accessors", [])
    if not 0 <= idx < len(accessors):
        return None
    acc = accessors[idx]
    if "bufferView" not in acc or "sparse" in acc:
        return None
    comp = _COMPONENT.get(acc.get("componentType"))
    n_comp = _TYPE_SIZE.get(acc.get("type", ""))
    if comp is None or n_comp is None:
        return None
    fmt_char, size = comp
    got = _view_bytes(doc, buffers, acc["bufferView"])
    if got is None:
        return None
    buf, view_off, stride = got
    elem_size = size * n_comp
    stride = stride or elem_size
    off = view_off + acc.get("byteOffset", 0)
    count = acc.get("count", 0)
    if off + stride * (count - 1) + elem_size > len(buf) if count else False:
        return None
    unpack = struct.Struct("<" + fmt_char * n_comp).unpack_from
    return [unpack(buf, off + i * stride) for i in range(count)]


# ------------------------------------------------------------------ meshes


def _mesh(doc: dict, buffers: list[bytes | None], index: int, m: dict) -> Mesh:
    accessors = doc.get("accessors", [])
    tris = 0
    verts = 0
    degenerate = 0
    bbox = BBox()
    materials: set[int] = set()
    all_uv = True
    for prim in m.get("primitives", []):
        attrs = prim.get("attributes", {})
        pos_idx = attrs.get("POSITION")
        if pos_idx is None or not 0 <= pos_idx < len(accessors):
            continue
        pos_acc = accessors[pos_idx]
        n_pos = pos_acc.get("count", 0)
        verts += n_pos
        if "TEXCOORD_0" not in attrs:
            all_uv = False
        materials.add(prim.get("material", -1))

        mn, mx = pos_acc.get("min"), pos_acc.get("max")
        if mn and mx and len(mn) == 3 and len(mx) == 3:
            bbox.add((mn[0], mn[1], mn[2]))
            bbox.add((mx[0], mx[1], mx[2]))

        mode = prim.get("mode", 4)
        idx_acc = prim.get("indices")
        n_idx = accessors[idx_acc].get("count", 0) if idx_acc is not None and 0 <= idx_acc < len(accessors) else n_pos
        if mode == 4:
            tris += n_idx // 3
        elif mode in (5, 6):
            tris += max(n_idx - 2, 0)
        else:
            continue  # points / lignes : pas de triangles

        if mode == 4:
            degenerate += _count_degenerate(doc, buffers, pos_idx, idx_acc, n_pos)
            if not (mn and mx):
                pts = _read_accessor(doc, buffers, pos_idx)
                if pts:
                    for p in pts:
                        bbox.add((p[0], p[1], p[2]))

    lo, hi = bbox.as_tuples()
    return Mesh(
        name=m.get("name") or f"mesh_{index}",
        triangles=tris,
        vertices=verts,
        degenerate_triangles=degenerate,
        bbox_min=lo,
        bbox_max=hi,
        has_uvs=all_uv if m.get("primitives") else None,
        material_count=len(materials) if materials else None,
    )


def _count_degenerate(doc, buffers, pos_idx, idx_acc, n_pos) -> int:
    pts = _read_accessor(doc, buffers, pos_idx)
    if pts is None:
        return 0
    if idx_acc is None:
        order = list(range(n_pos))
    else:
        raw = _read_accessor(doc, buffers, idx_acc)
        if raw is None:
            return 0
        order = [r[0] for r in raw]
    bad = 0
    for i in range(0, len(order) - 2, 3):
        try:
            a, b, c = pts[order[i]], pts[order[i + 1]], pts[order[i + 2]]
        except IndexError:
            return bad
        if is_degenerate(a[:3], b[:3], c[:3]):
            bad += 1
    return bad


# ---------------------------------------------------------------- textures


def _textures(doc: dict, buffers: list[bytes | None], base: Path) -> list[Texture]:
    out: list[Texture] = []
    for i, img in enumerate(doc.get("images", [])):
        data: bytes | None = None
        uri = img.get("uri")
        name = img.get("name") or (Path(unquote(uri)).name if uri and not uri.startswith("data:") else f"image_{i}")
        if uri is None and "bufferView" in img:
            got = _view_bytes(doc, buffers, img["bufferView"])
            if got:
                buf, off, _ = got
                length = doc["bufferViews"][img["bufferView"]].get("byteLength", 0)
                data = buf[off : off + length]
        elif uri and uri.startswith("data:"):
            try:
                data = base64.b64decode(uri.split(",", 1)[1])
            except Exception:
                data = None
        elif uri:
            try:
                data = (base / unquote(uri)).read_bytes()
            except OSError:
                data = None
        info = image_info(data) if data else None
        if info:
            out.append(Texture(name=name, width=info[1], height=info[2], fmt=info[0]))
        else:
            out.append(Texture(name=name))
    return out
