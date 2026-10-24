#!/usr/bin/env bash
# Downloads walkways, buildings and entrances around ASU Tempe from OpenStreetMap into data/osm_raw.json.
# Box: south, west, north, east. Widen it to cover more of Tempe.
set -euo pipefail
cd "$(dirname "$0")/.."
BOX="33.410,-111.945,33.432,-111.920"
QUERY="[out:json][timeout:120];
(
  way[\"highway\"~\"^(footway|path|pedestrian|steps|living_street|residential|service|cycleway|corridor|tertiary|secondary|primary|unclassified|track)$\"]($BOX);
  way[\"building\"]($BOX);
  relation[\"building\"]($BOX);
  node[\"entrance\"]($BOX);
);
out body;
>;
out skel qt;"
curl -sS --fail --max-time 180 -A "asu-map-hackathon/0.1" -H "Accept: application/json" \
  --data-urlencode "data=$QUERY" https://overpass-api.de/api/interpreter -o data/osm_raw.json
echo "Saved data/osm_raw.json ($(du -h data/osm_raw.json | cut -f1)). Now run: python3 tools/build_graph.py"
