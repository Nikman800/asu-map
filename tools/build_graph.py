#!/usr/bin/env python3
"""Turn OpenStreetMap data for ASU Tempe into the walking graph used by route.js.

Usage: python3 tools/build_graph.py [data/osm_raw.json] [data/overrides.json] [web/campus.json]

Standard library only. The output holds:
  nodes   {id: [lat, lon]}                    path junctions and building entrance points
  edges   [[a, b, meters, name, kind, [[lat, lon], ...]]]   walkable segments between junctions
  places  [{id, name, aliases, lat, lon, doors: [[node, meters], ...]}]   buildings and named spots
  meta.meeting_spots   place ids suggested when a group asks where to meet
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/osm_raw.json"
OVERRIDES = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data/overrides.json"
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "web/campus.json"

WALKABLE = {
    "footway", "path", "pedestrian", "steps", "living_street", "residential", "service", "cycleway",
    "corridor", "tertiary", "secondary", "primary", "unclassified", "track",
}
DOOR_SNAP_M = 80       # a building outline point this close to a path counts as a way in
CENTER_SNAP_M = 200    # fallback when no outline point is near a path
MAX_DOORS = 6


def meters(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class Grid:
    """Nearest-point lookup over graph nodes, bucketed by ~110 m cells."""

    def __init__(self, coords, ids):
        self.coords, self.cells = coords, defaultdict(list)
        for i in ids:
            self.cells[self.key(coords[i])].append(i)

    @staticmethod
    def key(p):
        return int(p[0] * 1000), int(p[1] * 1000)

    def nearest(self, p, limit):
        r = int(limit / 90) + 1
        ky, kx = self.key(p)
        best, best_d = None, limit
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                for i in self.cells.get((ky + dy, kx + dx), ()):
                    d = meters(p, self.coords[i])
                    if d < best_d:
                        best, best_d = i, d
        return best, best_d


def main():
    elements = json.loads(RAW.read_text())["elements"]
    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    closed = set(overrides.get("closed_ways", []))

    coords = {e["id"]: (e["lat"], e["lon"]) for e in elements if e["type"] == "node"}
    node_tags = {e["id"]: e.get("tags", {}) for e in elements if e["type"] == "node"}
    ways = {e["id"]: e for e in elements if e["type"] == "way"}

    # Walkable ways, plus any extra paths drawn by hand in overrides.json.
    paths = []
    for w in ways.values():
        t = w.get("tags", {})
        if t.get("highway") in WALKABLE and t.get("foot") != "no" and w["id"] not in closed:
            name = t.get("name") or ("stairs" if t["highway"] == "steps" else "")
            paths.append((w["nodes"], name, t["highway"]))
    next_id = -1
    for extra in overrides.get("extra_paths", []):
        ids = []
        for lat, lon in extra["points"]:
            coords[next_id] = (lat, lon)
            ids.append(next_id)
            next_id -= 1
        paths.append((ids, extra.get("name", ""), extra.get("kind", "footway")))

    on_path = {n for ids, _, _ in paths for n in ids}
    grid = Grid(coords, on_path)

    # Hand-drawn paths join the network at their nearest existing path point.
    for ids, _, _ in paths:
        for end in (ids[0], ids[-1]):
            if end < 0:
                near, d = grid.nearest(coords[end], 30)
                if near is not None and near != end and near > 0:
                    paths.append(([end, near], "", "footway"))

    # Places: named buildings from OSM, then hand-added places.
    places = []
    for e in elements:
        t = e.get("tags", {})
        if e["type"] not in ("way", "relation") or "building" not in t or "name" not in t:
            continue
        if e["type"] == "way":
            outline = e["nodes"]
        else:
            outline = [n for m in e.get("members", []) if m["type"] == "way" and m.get("role") == "outer"
                       for n in ways.get(m["ref"], {}).get("nodes", [])]
        outline = [n for n in outline if n in coords]
        if not outline:
            continue
        places.append({"name": t["name"], "ref": t.get("ref") or t.get("short_name") or "", "outline": outline})
    # OSM often splits one building into several outlines; treat same-named ones as one place.
    merged = {}
    for p in places:
        key = p["name"].lower()
        if key in merged:
            merged[key]["outline"] += p["outline"]
            merged[key]["ref"] = merged[key]["ref"] or p["ref"]
        else:
            merged[key] = p
    places = list(merged.values())
    for p in overrides.get("places", []):
        places.append({"name": p["name"], "ref": p.get("id", ""), "point": (p["lat"], p["lon"]),
                       "aliases": p.get("aliases", [])})

    # Snap each place's ways in (OSM entrances first, else outline corners) onto the path network.
    snapped = set()
    out_places, used_ids = [], set()
    extra_aliases = {k.lower(): v for k, v in overrides.get("aliases", {}).items()}
    for p in places:
        if "outline" in p:
            pts = [coords[n] for n in p["outline"]]
            center = (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))
            entrances = [coords[n] for n in p["outline"] if "entrance" in node_tags.get(n, {})]
            candidates = entrances or pts
        else:
            center = candidates = p["point"]
            candidates = [p["point"]]
        doors = {}
        for q in candidates:
            near, d = grid.nearest(q, DOOR_SNAP_M)
            if near is not None and d < doors.get(near, math.inf):
                doors[near] = d
        if not doors:
            near, d = grid.nearest(center, CENTER_SNAP_M)
            if near is None:
                print(f"skipped (no path nearby): {p['name']}", file=sys.stderr)
                continue
            doors[near] = d
        best = sorted(doors.items(), key=lambda kv: kv[1])
        # Keep doors spread around the building, not six corners of one wall.
        picked = []
        for n, d in best:
            if all(meters(coords[n], coords[m]) > 25 for m, _ in picked):
                picked.append((n, d))
            if len(picked) == MAX_DOORS:
                break
        snapped.update(n for n, _ in picked)

        ref = p["ref"]
        pid = ref if len(ref) > 1 and not ref.isdigit() else slug(p["name"])
        m = re.search(r"\((\w+)\)\s*(\d+)$", p["name"])
        if m:  # "Interdisciplinary Science and Technology Building (ISTB) 1" -> ISTB1
            pid = m.group(1) + m.group(2)
        base, k = pid, 2
        while pid.lower() in used_ids:
            pid, k = f"{base}-{k}", k + 1
        used_ids.add(pid.lower())
        aliases = sorted({a for a in [ref, *(p.get("aliases") or []),
                                      *extra_aliases.get(pid.lower(), []),
                                      *extra_aliases.get(p["name"].lower(), [])] if len(a) > 1 and not a.isdigit()} - {pid})
        out_places.append({"id": pid, "name": p["name"], "aliases": aliases,
                           "lat": round(center[0], 6), "lon": round(center[1], 6),
                           "doors": [[str(n), round(d)] for n, d in picked]})

    # Compress: keep only junctions, path ends and door points as graph nodes.
    uses = defaultdict(int)
    for ids, _, _ in paths:
        for n in ids:
            uses[n] += 1
    keep = set(snapped)
    for ids, _, _ in paths:
        keep.update((ids[0], ids[-1]))
        keep.update(n for n in ids if uses[n] > 1)

    edges = []
    for ids, name, kind in paths:
        seg = [ids[0]]
        for n in ids[1:]:
            seg.append(n)
            if n in keep:
                if seg[0] != seg[-1]:
                    geom = [coords[i] for i in seg]
                    length = sum(meters(geom[i], geom[i + 1]) for i in range(len(geom) - 1))
                    edges.append([seg[0], seg[-1], round(length, 1), name, kind,
                                  [[round(a, 5), round(b, 5)] for a, b in geom]])
                seg = [n]

    used = {e[0] for e in edges} | {e[1] for e in edges}
    ids = {p["id"] for p in out_places}
    spots = [s for s in overrides.get("meeting_spots", []) if s in ids]
    for s in set(overrides.get("meeting_spots", [])) - ids:
        print(f"meeting spot not found: {s}", file=sys.stderr)
    out = {
        "meta": {
            "source": "OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)",
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "walk_m_per_min": 80,
            "meeting_spots": spots,
            "map_url": overrides.get("map_url", ""),
        },
        "nodes": {str(n): [round(coords[n][0], 6), round(coords[n][1], 6)] for n in sorted(used)},
        "edges": [[str(a), str(b), *rest] for a, b, *rest in edges],
        "places": sorted(out_places, key=lambda p: p["name"]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(out['nodes'])} nodes, {len(edges)} edges, {len(out_places)} places -> {OUT} "
          f"({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
