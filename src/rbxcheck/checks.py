"""Règles de validation appliquées aux maillages lus."""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .errors import ParseError
from .models import Issue, Mesh, ParsedFile, Report, Severity
from .parsers import parse_file


@dataclass(frozen=True)
class Profile:
    """Budget de triangles selon le type d'asset."""

    name: str
    max_triangles: int  # au-delà : erreur
    warn_triangles: int | None  # au-delà : avertissement
    description: str


PROFILES: dict[str, Profile] = {
    "mesh": Profile(
        "mesh", 20_000, 10_000,
        "MeshPart in an experience (props, environment). Hard cap ~20k, comfortable under 10k.",
    ),
    "accessory": Profile(
        "accessory", 4_000, None,
        "Rigid UGC accessory (hat, back item...). Hard cap 4k.",
    ),
}


@dataclass(frozen=True)
class Config:
    profile: Profile = PROFILES["mesh"]
    max_texture: int = 4096  # au-delà : erreur
    comfy_texture: int = 1024  # au-delà : info
    max_file_mb: float = 20.0
    max_dimension: float = 2048.0  # taille max d'une pièce Roblox (studs)
    tiny_dimension: float = 0.01  # tout est plus petit : probable problème d'échelle

    def with_overrides(self, max_triangles: int | None = None, warn_triangles: int | None = None, profile: str | None = None) -> "Config":
        prof = PROFILES[profile] if profile else self.profile
        if max_triangles is not None or warn_triangles is not None:
            prof = Profile(
                prof.name,
                max_triangles if max_triangles is not None else prof.max_triangles,
                warn_triangles if warn_triangles is not None else prof.warn_triangles,
                prof.description,
            )
        return Config(
            profile=prof,
            max_texture=self.max_texture,
            comfy_texture=self.comfy_texture,
            max_file_mb=self.max_file_mb,
            max_dimension=self.max_dimension,
            tiny_dimension=self.tiny_dimension,
        )


_DEFAULT_NAME = re.compile(
    r"^(cube|sphere|plane|cylinder|cone|torus|circle|icosphere|uv.?sphere|suzanne|monkey|grid|mesh|object|empty|geometry)([._ ]?\d+)?$",
    re.IGNORECASE,
)


def check_file(path: str | os.PathLike, config: Config | None = None) -> Report:
    config = config or Config()
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as e:
        return Report(
            path=str(p), fmt="?", size_bytes=0,
            issues=[Issue(Severity.ERROR, "READ", f"Cannot read file: {e.strerror or e}")],
        )

    try:
        parsed = parse_file(p)
    except ParseError as e:
        return Report(
            path=str(p), fmt=p.suffix.upper().lstrip(".") or "?", size_bytes=size,
            issues=[Issue(Severity.ERROR, "PARSE", str(e))],
        )

    report = Report(path=str(p), fmt=parsed.fmt, size_bytes=size, meshes=parsed.meshes, textures=parsed.textures)
    report.issues.extend(evaluate(parsed, size, config))
    return report


def evaluate(parsed: ParsedFile, size_bytes: int, config: Config) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda sev, code, msg, mesh=None: issues.append(Issue(sev, code, msg, mesh))  # noqa: E731

    if not parsed.meshes:
        add(Severity.ERROR, "NO_MESH", "No mesh found in this file.")

    if size_bytes > config.max_file_mb * 1024 * 1024:
        add(Severity.ERROR, "FILE_SIZE",
            f"File is {size_bytes / 1024 / 1024:.1f} MB (limit ~{config.max_file_mb:g} MB).")

    names = Counter(m.name for m in parsed.meshes)
    prof = config.profile
    for m in parsed.meshes:
        _check_mesh(m, config, prof, names, add)

    for t in parsed.textures:
        if t.width and t.height:
            biggest = max(t.width, t.height)
            if biggest > config.max_texture:
                add(Severity.ERROR, "TEXTURE_SIZE",
                    f"Texture '{t.name}' is {t.width}x{t.height} (max {config.max_texture}).")
            elif biggest > config.comfy_texture:
                add(Severity.INFO, "TEXTURE_BIG",
                    f"Texture '{t.name}' is {t.width}x{t.height}. {config.comfy_texture}x{config.comfy_texture} is usually enough and saves memory.")
            if (t.width & (t.width - 1)) or (t.height & (t.height - 1)):
                add(Severity.INFO, "TEXTURE_NPOT",
                    f"Texture '{t.name}' is {t.width}x{t.height}: not a power of two.")

    for note in parsed.notes:
        add(Severity.INFO, "NOTE", note)
    return issues


def _check_mesh(m: Mesh, config: Config, prof: Profile, names: Counter, add) -> None:
    if m.triangles > prof.max_triangles:
        add(Severity.ERROR, "TRI_LIMIT",
            f"{m.triangles:,} triangles (limit {prof.max_triangles:,} for profile '{prof.name}'). Decimate or split the mesh.", m.name)
    elif prof.warn_triangles is not None and m.triangles > prof.warn_triangles:
        add(Severity.WARNING, "TRI_HIGH",
            f"{m.triangles:,} triangles (comfortable budget is {prof.warn_triangles:,}).", m.name)

    if m.degenerate_triangles:
        add(Severity.WARNING, "DEGENERATE",
            f"{m.degenerate_triangles:,} degenerate (zero-area) triangles. Clean up with Merge by Distance / Delete Loose.", m.name)

    if m.has_uvs is False:
        add(Severity.WARNING, "NO_UV", "No UV map: textures cannot be applied.", m.name)

    if m.material_count and m.material_count > 1:
        add(Severity.WARNING, "MULTI_MATERIAL",
            f"{m.material_count} materials on one mesh. Studio applies a single texture per MeshPart: merge materials or split the mesh.", m.name)

    size = m.size
    if size is not None:
        biggest = max(size)
        if biggest > config.max_dimension:
            add(Severity.WARNING, "TOO_BIG",
                f"Largest dimension is {biggest:g} units (> {config.max_dimension:g}). Check the export scale.", m.name)
        elif 0 < biggest < config.tiny_dimension:
            add(Severity.WARNING, "TOO_SMALL",
                f"Largest dimension is only {biggest:g} units. Check the export scale.", m.name)
        elif biggest == 0:
            add(Severity.WARNING, "FLAT_POINT", "Mesh has zero size on every axis.", m.name)

    if _DEFAULT_NAME.match(m.name):
        add(Severity.WARNING, "DEFAULT_NAME", f"'{m.name}' looks like a default name. Give it a meaningful name.", m.name)
    elif " " in m.name or not m.name.isascii():
        add(Severity.INFO, "NAME_CHARS",
            "Name has spaces or non-ASCII characters: awkward to reference from Luau.", m.name)
    if names[m.name] > 1:
        add(Severity.WARNING, "DUP_NAME", f"Name used by {names[m.name]} meshes.", m.name)
