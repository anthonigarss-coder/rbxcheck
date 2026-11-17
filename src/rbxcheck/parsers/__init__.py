"""Parseurs de formats 3D. Chaque parseur renvoie un ``ParsedFile``."""

from __future__ import annotations

from pathlib import Path

from ..errors import ParseError
from ..models import ParsedFile
from . import fbx, gltf, obj, stl

PARSERS = {
    ".obj": obj.parse,
    ".stl": stl.parse,
    ".gltf": gltf.parse,
    ".glb": gltf.parse,
    ".fbx": fbx.parse,
}

SUPPORTED_EXTENSIONS = tuple(sorted(PARSERS))


def parse_file(path: str | Path) -> ParsedFile:
    p = Path(path)
    parser = PARSERS.get(p.suffix.lower())
    if parser is None:
        raise ParseError(
            f"Unsupported format '{p.suffix}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    return parser(p)
