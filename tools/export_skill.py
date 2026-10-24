#!/usr/bin/env python3
"""Copy the campus router into a Cubbie Skill folder.

Usage: python3 tools/export_skill.py <skill-folder>      e.g. ../DevHacks_26

Writes scripts/route.mjs, scripts/route.js and a slim assets/campus.json (no drawing shapes, so it stays
under Cubbie's 1 MiB per-file limit). Run it again after rebuilding web/campus.json.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 1024 * 1024


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip())
    skill = Path(sys.argv[1]).resolve()
    if not (skill / "SKILL.md").exists():
        sys.exit(f"No SKILL.md in {skill}")

    data = json.loads((ROOT / "web/campus.json").read_text())
    overrides = json.loads((ROOT / "data/overrides.json").read_text())
    data["edges"] = [e[:5] for e in data["edges"]]
    for p in data["places"]:
        p["lat"], p["lon"] = round(p["lat"], 5), round(p["lon"], 5)
    if overrides.get("map_url"):
        data["meta"]["map_url"] = overrides["map_url"]

    (skill / "scripts").mkdir(exist_ok=True)
    (skill / "assets").mkdir(exist_ok=True)
    shutil.copy(ROOT / "tools/route.mjs", skill / "scripts/route.mjs")
    shutil.copy(ROOT / "web/route.js", skill / "scripts/route.js")
    out = skill / "assets/campus.json"
    out.write_text(json.dumps(data, separators=(",", ":")))

    size = out.stat().st_size
    print(f"Exported to {skill}: assets/campus.json is {size // 1024} KB")
    if size > LIMIT:
        sys.exit("Too big for Cubbie (1 MiB per file): trim the data before publishing.")


if __name__ == "__main__":
    main()
