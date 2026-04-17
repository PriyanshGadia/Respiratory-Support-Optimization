#!/usr/bin/env python
# =============================================================================
# 25_phase3_markdown_compact.py  —  Phase 3 markdown compactor
# Version: 1.0  |  2026-03-20
#
# Consolidates project markdown into a single compendium and optional index,
# with optional cleanup of redundant generated markdown artifacts.
# =============================================================================

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
from datetime import datetime, timezone

import config as C

ROOT = os.path.abspath(os.path.join(C.ANALYSIS_DIR, ".."))
DOCS_DIR = os.path.join(ROOT, "docs")
LOGS_MD_GLOB = os.path.join(C.LOGS_DIR, "*.md")

OUT_MD = os.path.join(C.LOGS_DIR, "phase3_markdown_compendium.md")
OUT_JSON = os.path.join(C.LOGS_DIR, "phase3_markdown_index.json")

EXCLUDE_NAMES = {
    os.path.basename(OUT_MD),
    os.path.basename(OUT_JSON),
}

CLEANUP_GENERATED_MD = {
    os.path.join(C.LOGS_DIR, "phase3_closure_plan.md"),
}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _collect_markdown_files() -> list[str]:
    files: list[str] = []

    # Keep docs primary and stable order.
    if os.path.isdir(DOCS_DIR):
        files.extend(sorted(glob.glob(os.path.join(DOCS_DIR, "*.md"))))

    # Include log markdowns for execution evidence and templates.
    files.extend(sorted(glob.glob(LOGS_MD_GLOB)))

    dedup: list[str] = []
    seen = set()
    for p in files:
        name = os.path.basename(p)
        if name in EXCLUDE_NAMES:
            continue
        ap = os.path.abspath(p)
        if ap in seen:
            continue
        seen.add(ap)
        dedup.append(ap)
    return dedup


def _rel(path: str) -> str:
    return os.path.relpath(path, C.ANALYSIS_DIR).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate markdown files into compact compendium")
    parser.add_argument("--cleanup-generated-markdown", action="store_true", help="Remove redundant generated markdown outputs")
    args = parser.parse_args()

    os.makedirs(C.LOGS_DIR, exist_ok=True)

    files = _collect_markdown_files()
    removed: list[str] = []

    if args.cleanup_generated_markdown:
        for p in sorted(CLEANUP_GENERATED_MD):
            if os.path.exists(p):
                try:
                    os.remove(p)
                    removed.append(_rel(p))
                except OSError:
                    pass

    index = []
    md_lines = [
        "# Phase 3 Markdown Compendium",
        "",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"- Source markdown files: {len(files)}",
        "",
        "## Index",
    ]

    for p in files:
        if not os.path.exists(p):
            continue
        meta = {
            "path": _rel(p),
            "bytes": os.path.getsize(p),
            "sha256": _sha256(p),
        }
        index.append(meta)
        md_lines.append(f"- {meta['path']}")

    md_lines.extend(["", "---", ""])

    for meta in index:
        p = os.path.join(C.ANALYSIS_DIR, meta["path"].replace("/", os.sep))
        if not os.path.exists(p):
            continue
        md_lines.append(f"## Source: {meta['path']}")
        md_lines.append("")
        md_lines.append("```markdown")
        md_lines.append(_read(p).rstrip())
        md_lines.append("```")
        md_lines.append("")

    if removed:
        md_lines.append("## Housekeeping")
        for r in removed:
            md_lines.append(f"- Removed redundant generated markdown: {r}")
        md_lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines) + "\n")

    out = {
        "version": "1.0",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_count": len(index),
        "sources": index,
        "cleanup_generated_markdown_enabled": bool(args.cleanup_generated_markdown),
        "removed_generated_markdown": removed,
        "compendium": _rel(OUT_MD),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    print(f"Saved: {OUT_MD}")
    print(f"Saved: {OUT_JSON}")
    if removed:
        print(f"Removed generated markdown files: {len(removed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
