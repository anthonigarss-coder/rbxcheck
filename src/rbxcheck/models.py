"""Structures de données communes à tous les parseurs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2

    @property
    def label(self) -> str:
        return self.name


@dataclass
class Texture:
    name: str
    width: int | None = None
    height: int | None = None
    fmt: str | None = None


@dataclass
class Mesh:
    """Un maillage lu dans un fichier (un fichier peut en contenir plusieurs)."""

    name: str
    triangles: int = 0
    vertices: int = 0
    degenerate_triangles: int = 0
    bbox_min: tuple[float, float, float] | None = None
    bbox_max: tuple[float, float, float] | None = None
    # None = le format ne permet pas de le savoir
    has_uvs: bool | None = None
    material_count: int | None = None

    @property
    def size(self) -> tuple[float, float, float] | None:
        if self.bbox_min is None or self.bbox_max is None:
            return None
        return (
            self.bbox_max[0] - self.bbox_min[0],
            self.bbox_max[1] - self.bbox_min[1],
            self.bbox_max[2] - self.bbox_min[2],
        )


@dataclass
class ParsedFile:
    """Résultat brut d'un parseur."""

    fmt: str
    meshes: list[Mesh] = field(default_factory=list)
    textures: list[Texture] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    mesh: str | None = None


@dataclass
class Report:
    path: str
    fmt: str
    size_bytes: int
    meshes: list[Mesh] = field(default_factory=list)
    textures: list[Texture] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def total_triangles(self) -> int:
        return sum(m.triangles for m in self.meshes)

    def count(self, severity: Severity) -> int:
        return sum(1 for i in self.issues if i.severity == severity)

    @property
    def errors(self) -> int:
        return self.count(Severity.ERROR)

    @property
    def warnings(self) -> int:
        return self.count(Severity.WARNING)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "format": self.fmt,
            "size_bytes": self.size_bytes,
            "total_triangles": self.total_triangles,
            "meshes": [
                {
                    "name": m.name,
                    "triangles": m.triangles,
                    "vertices": m.vertices,
                    "degenerate_triangles": m.degenerate_triangles,
                    "size": list(m.size) if m.size else None,
                    "has_uvs": m.has_uvs,
                    "material_count": m.material_count,
                }
                for m in self.meshes
            ],
            "textures": [
                {"name": t.name, "width": t.width, "height": t.height, "format": t.fmt}
                for t in self.textures
            ],
            "issues": [
                {
                    "severity": i.severity.label,
                    "code": i.code,
                    "message": i.message,
                    "mesh": i.mesh,
                }
                for i in self.issues
            ],
            "errors": self.errors,
            "warnings": self.warnings,
        }
