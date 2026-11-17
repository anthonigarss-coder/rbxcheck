"""Interface en ligne de commande : ``rbxcheck model.fbx``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .checks import PROFILES, Config, check_file
from .parsers import SUPPORTED_EXTENSIONS
from .report import print_summary, render_json, render_text, use_color, verdict_for


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rbxcheck",
        description="Check 3D models (OBJ, STL, glTF/GLB, FBX) before importing them into Roblox Studio.",
        epilog="Exit codes: 0 = all good, 1 = at least one file failed, 2 = usage error.",
    )
    p.add_argument("paths", nargs="+", help="model files, or folders to scan recursively")
    p.add_argument("-p", "--profile", choices=sorted(PROFILES), default="mesh",
                   help="triangle budget: " + "; ".join(f"{k} = {v.description}" for k, v in PROFILES.items()))
    p.add_argument("--max-triangles", type=int, metavar="N", help="override the triangle hard limit")
    p.add_argument("--warn-triangles", type=int, metavar="N", help="override the triangle warning threshold")
    p.add_argument("--strict", action="store_true", help="treat warnings as failures")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--no-color", action="store_true", help="disable colors")
    p.add_argument("-V", "--version", action="version", version=f"rbxcheck {__version__}")
    return p


def collect_files(paths: list[str]) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    missing: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS))
        elif p.exists():
            files.append(p)
        else:
            missing.append(raw)
    return files, missing


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    files, missing = collect_files(args.paths)
    for m in missing:
        print(f"rbxcheck: no such file or folder: {m}", file=sys.stderr)
    if not files:
        print("rbxcheck: no model files to check.", file=sys.stderr)
        return 2

    config = Config().with_overrides(args.max_triangles, args.warn_triangles, args.profile)
    reports = [check_file(f, config) for f in files]

    if args.json:
        print(render_json(reports))
    else:
        color = use_color(sys.stdout) and not args.no_color
        for r in reports:
            print(render_text(r, color=color, strict=args.strict))
            print()
        if len(reports) > 1:
            print_summary(reports, args.strict)

    failed = any(not verdict_for(r, args.strict)[1] for r in reports) or bool(missing)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
