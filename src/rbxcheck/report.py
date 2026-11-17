"""Affichage texte et JSON des rapports."""

from __future__ import annotations

import json
import os
import sys

from .models import Report, Severity

_COLORS = {Severity.ERROR: "31", Severity.WARNING: "33", Severity.INFO: "36"}


def use_color(stream) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)()) and "NO_COLOR" not in os.environ


def _paint(text: str, code: str, color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if color else text


def render_text(report: Report, color: bool = False, strict: bool = False) -> str:
    out: list[str] = []
    out.append(_paint(report.path, "1", color))
    out.append(f"  format: {report.fmt}   size: {report.size_bytes / 1024:.1f} KB   triangles: {report.total_triangles:,}   meshes: {len(report.meshes)}")
    for m in report.meshes:
        dims = ""
        if m.size:
            dims = "   size: %g x %g x %g" % m.size
        out.append(f"    - {m.name}: {m.triangles:,} tris, {m.vertices:,} verts{dims}")
    for t in report.textures:
        dims = f"{t.width}x{t.height}" if t.width else "size unknown"
        out.append(f"    * texture {t.name}: {dims}")

    if report.issues:
        out.append("")
        for i in sorted(report.issues, key=lambda x: -int(x.severity)):
            tag = _paint(f"{i.severity.label:7}", _COLORS[i.severity], color)
            where = f"[{i.mesh}] " if i.mesh else ""
            out.append(f"  {tag} {i.code:<14} {where}{i.message}")

    verdict = verdict_for(report, strict)
    out.append("")
    out.append(_paint(verdict[0], "32" if verdict[1] else "31", color) + f"  ({report.errors} error(s), {report.warnings} warning(s))")
    return "\n".join(out)


def verdict_for(report: Report, strict: bool) -> tuple[str, bool]:
    failed = report.errors > 0 or (strict and report.warnings > 0)
    return ("FAIL" if failed else "OK"), not failed


def render_json(reports: list[Report]) -> str:
    return json.dumps([r.to_dict() for r in reports], indent=2)


def print_summary(reports: list[Report], strict: bool, stream=None) -> None:
    stream = stream or sys.stdout
    bad = sum(1 for r in reports if not verdict_for(r, strict)[1])
    print(f"\n{len(reports)} file(s) checked, {bad} failed.", file=stream)
