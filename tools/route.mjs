#!/usr/bin/env node
// Command-line access to the campus map, for a Cubbie Skill script or a Track 2/3 bot.
//
//   node tools/route.mjs route "MU" "Hayden Library" [--live]
//     --live: the map link starts from the phone's location when tapped, falling back to <from>
//   node tools/route.mjs meet ISTB4 SRC LIB [--at LIB,MU,noble]
//   node tools/route.mjs find hayden
//   add --json for machine-readable output

import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Runs from this project (tools/ next to web/) or from a Cubbie Skill (scripts/ next to assets/).
const here = (p) => fileURLToPath(new URL(p, import.meta.url));
const { CampusMap } = await import(existsSync(here("./route.js")) ? "./route.js" : "../web/route.js");
const dataPath = [here("../assets/campus.json"), here("../web/campus.json")].find(existsSync);
const data = JSON.parse(readFileSync(dataPath));
const map = new CampusMap(data);
// Links are printed only once the web map is hosted somewhere (overrides.json "map_url", or ASU_MAP_URL).
const MAP_URL = process.env.ASU_MAP_URL || data.meta.map_url || "";

const args = process.argv.slice(2);
const json = args.includes("--json");
const live = args.includes("--live");
const atIdx = args.indexOf("--at");
const at = atIdx >= 0 ? args[atIdx + 1].split(",") : null;
const [cmd, ...rest] = args.filter((a, i) => a !== "--json" && a !== "--live" && (atIdx < 0 || (i !== atIdx && i !== atIdx + 1)));

const link = (params) => (MAP_URL ? `${MAP_URL}?${new URLSearchParams(params)}` : undefined);
const out = (obj, text) => console.log(json ? JSON.stringify(obj) : text);

try {
  if (cmd === "route" && rest.length === 2) {
    const r = map.route(rest[0], rest[1]);
    const url = link(live ? { from: "here", to: r.to.id, fallback: r.from.id } : { from: r.from.id, to: r.to.id });
    out(
      { from: r.from.name, to: r.to.name, meters: r.meters, minutes: r.minutes, steps: r.steps, url },
      `${r.from.name} -> ${r.to.name}: about ${r.minutes} min walk (${r.meters} m)\n` +
        r.steps.map((s, i) => `${i + 1}. ${s}`).join("\n") + (url ? `\n${url}` : ""),
    );
  } else if (cmd === "meet" && rest.length >= 2) {
    const { origins, options } = map.meetup(rest, { candidates: at });
    const rows = options.map((o) => ({
      place: o.place.name,
      minutes: Object.fromEntries(origins.map((p, i) => [p.name, o.minutes[i]])),
      url: link({ from: origins.map((p) => p.id).join(","), to: o.place.id }),
    }));
    out(
      rows,
      rows
        .map((r, i) => `${i + 1}. ${r.place}: ` +
          Object.entries(r.minutes).map(([k, m]) => `${m} min from ${k}`).join(", ") + (r.url ? `\n   ${r.url}` : ""))
        .join("\n"),
    );
  } else if (cmd === "find" && rest.length) {
    const found = map.searchPlaces(rest.join(" "), 8);
    out(
      found.map((p) => ({ id: p.id, name: p.name, aliases: p.aliases })),
      found.length ? found.map((p) => `${p.id}\t${p.name}`).join("\n") : "No matching place.",
    );
  } else {
    console.log('Usage: route <from> <to> [--live] | meet <place> <place> [...] [--at a,b,c] | find <text>   [--json]');
    process.exit(2);
  }
} catch (e) {
  console.log(e.message.startsWith("Unknown place") ? `${e.message}. Try: find <part of the name>` : e.message);
  process.exit(1);
}
