# ASU Campus Walk

Walking routes and fair meeting spots on ASU's Tempe campus, built from OpenStreetMap and shown on a 2D map or
the team's 3D campus model. One routing engine (`web/route.js`) serves the web pages, the Cubbie Skill and any
Track 2 or 3 bot.

```
data/overrides.json   hand edits on top of OpenStreetMap (nicknames, meeting spots, extra or closed paths)
data/osm_raw.json     downloaded OpenStreetMap data (not committed; tools/fetch_osm.sh recreates it)
tools/fetch_osm.sh    downloads walkways, buildings and entrances around campus
tools/build_graph.py  turns the download + overrides into web/campus.json
tools/fit_stl.py      lines a 3D-print STL of campus up with real coordinates -> web/model.json
tools/route.mjs       command line: routes, meeting spots, place search
web/route.js          the routing engine (browser and Node, no dependencies)
web/index.html        2D map
web/3d.html           3D view of web/campus-model.stl with the same routes
```

## Try it

```bash
node tools/route.mjs route "Tempe Transportation Center" MU
node tools/route.mjs meet ISTB4 SRC "Tooker House A"            # fairest of the meeting spots
node tools/route.mjs meet ISTB4 SRC --at LIB,MU,noble            # choose among these
node tools/route.mjs find library                                # look up place ids
node tools/route.mjs --json route MU LIB                         # for bots and scripts

cd web && python3 -m http.server 8000
# http://localhost:8000/?from=MU&to=LIB
# http://localhost:8000/?from=ISTB4,SRC,tooker-house-a          (group: picks the meeting spot)
# http://localhost:8000/3d.html?from=ISTB4,SRC,tooker-house-a
# http://localhost:8000/?from=here&to=MU                         (live, from the phone's location)
```

`from=here` starts from the phone's location: the page asks for permission, shows a live blue dot and re-plans
the route every 15 m as the student walks ("Use my location" does the same). The position stays in the browser;
the page is static and sends it nowhere. Browsers allow location only on https pages or localhost.

Links use place ids (`MU`, `LIB`, `ISTB4`, `SRC`, or a name slug such as `tooker-house-a`); `find` lists them.
Walking speed is 80 m per minute, and stairs count 30% longer.

## Rebuilding the data

```bash
bash tools/fetch_osm.sh            # only when you want fresh OpenStreetMap data
python3 tools/build_graph.py       # after any change to data/overrides.json
```

`data/overrides.json` is the file to edit by hand:

| Key | What it does | Example |
|---|---|---|
| `aliases` | Extra names for a place, keyed by its id or full name | `"SRC": ["SDFC", "the gym"]` |
| `meeting_spots` | Place ids suggested when a group asks where to meet | `["MU", "LIB", ...]` |
| `places` | Places OpenStreetMap lacks, such as a courtyard or bus stop | `{"id": "hayden-lawn", "name": "Hayden Lawn", "lat": 33.4195, "lon": -111.9345, "aliases": ["the lawn"]}` |
| `extra_paths` | Walkways OpenStreetMap lacks; each end joins the nearest path within 30 m | `{"name": "Palm Walk shortcut", "points": [[33.4201, -111.9320], [33.4205, -111.9318]]}` |
| `closed_ways` | OpenStreetMap way ids to leave out, such as a path closed for construction | `[123456789]` |

Fixes that help everyone are better made in OpenStreetMap itself (openstreetmap.org, free account), then picked
up with `fetch_osm.sh`. Naming unnamed walkways there also improves the step-by-step directions, which say
"the walkway" for paths without a name.

## The 3D model

`web/campus-model.stl` is the team's first-draft print model (`asu-tempe-campus first draft.stl`). It is
1:10,000 scale: x points east and y north in millimetres, z is height, with the base at 2.4 mm and roads at
2.53 mm. `tools/fit_stl.py` matched 195 of its 228 buildings to OpenStreetMap with a median error of 1.5 m and saved
the result in `web/model.json`, which `3d.html` uses to draw routes on the model.

For a new version of the model, keep the same orientation (north = +y) and run:

```bash
cp "<new model>.stl" web/campus-model.stl
python3 tools/fit_stl.py web/campus-model.stl
```

A good fit reports most buildings matched and a median error of a few metres. The model shows the campus but is
not used for routing; walkways come from OpenStreetMap, because the model has streets but few campus paths and
no building names.

## Inside the Cubbie Skill

The `class-to-map` Skill (github.com/owen0124/DevHacks_26) carries its own copy of the router so Cubbie can run
it in the student's sandbox with Node, with no keys or network. After rebuilding the data, refresh that copy and
push it:

```bash
python3 tools/export_skill.py ../DevHacks_26     # writes scripts/route.mjs, scripts/route.js, assets/campus.json
```

The export drops the drawing shapes to stay under Cubbie's 1 MiB per-file limit. It also carries `map_url` from
`data/overrides.json`, so the script prints a link to each route on the hosted map.

## Publishing

Live at https://nikman800.github.io/asu-map/ — GitHub Pages publishes the `web` folder on every push to `main`
(`.github/workflows/pages.yml`). `map_url` in `data/overrides.json` holds that address, so `route.mjs` and the
Cubbie Skill print links to it. If the map moves, change `map_url`, rebuild and export to the Skill again.

## Credits and license

Map data © OpenStreetMap contributors, available under the Open Database License
(https://www.openstreetmap.org/copyright). Keep this credit on any page or video that shows the map.
