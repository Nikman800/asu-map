// Walking routes on ASU's Tempe campus. Works in the browser and in Node (ES module, no dependencies).
//
//   const map = new CampusMap(await (await fetch("campus.json")).json());
//   map.route("MU", "Hayden Library")      -> { from, to, meters, minutes, path, steps }
//   map.meetup(["ISTB4", "SRC", "LIB"])    -> places ranked by the fairest walk for everyone

const STAIRS_FACTOR = 1.3; // stairs take longer than their length suggests

export class CampusMap {
  constructor(data) {
    this.meta = data.meta;
    this.nodes = data.nodes;
    this.places = data.places;
    this.edges = data.edges;
    this.mPerMin = data.meta.walk_m_per_min || 80;
    this.adj = new Map();
    data.edges.forEach(([a, b, len, , kind], i) => {
      const cost = kind === "steps" ? len * STAIRS_FACTOR : len;
      for (const [x, y] of [[a, b], [b, a]]) {
        if (!this.adj.has(x)) this.adj.set(x, []);
        this.adj.get(x).push([y, cost, i]);
      }
    });
    this.index = new Map();
    // Ids win over names, and names over nicknames, when two places share a key.
    for (const field of [(p) => p.aliases, (p) => [p.name], (p) => [p.id]]) {
      for (const p of this.places) for (const key of field(p)) this.index.set(norm(key), p);
    }
  }

  // Finds a place by id, nickname or name. Returns null when nothing is close.
  findPlace(query) {
    return this.searchPlaces(query, 1)[0] || null;
  }

  searchPlaces(query, limit = 5) {
    const q = norm(query);
    if (!q) return [];
    if (this.index.has(q)) return [this.index.get(q)];
    const words = q.split(" ");
    const scored = [];
    for (const p of this.places) {
      const keys = [p.id, p.name, ...p.aliases].map(norm);
      let score = 0;
      for (const k of keys) {
        if (k.startsWith(q)) score = Math.max(score, 3);
        else if (k.includes(q)) score = Math.max(score, 2);
        else if (words.every((w) => k.includes(w))) score = Math.max(score, 1);
      }
      if (score) scored.push([score, -p.name.length, p]);
    }
    scored.sort((a, b) => b[0] - a[0] || b[1] - a[1]);
    return scored.slice(0, limit).map((s) => s[2]);
  }

  // Shortest walking distances from a place (every door is a starting point) to every node.
  distancesFrom(place) {
    const dist = new Map();
    const prev = new Map();
    const heap = new MinHeap();
    for (const [n, d] of place.doors) {
      if (d < (dist.get(n) ?? Infinity)) {
        dist.set(n, d);
        heap.push(d, n);
      }
    }
    while (heap.size) {
      const [d, n] = heap.pop();
      if (d > dist.get(n)) continue;
      for (const [m, cost, edge] of this.adj.get(n) || []) {
        const nd = d + cost;
        if (nd < (dist.get(m) ?? Infinity)) {
          dist.set(m, nd);
          prev.set(m, [n, edge]);
          heap.push(nd, m);
        }
      }
    }
    return { dist, prev };
  }

  // Best door of `place` given distances from somewhere: [meters, door node].
  arrival(place, dist) {
    let best = [Infinity, null];
    for (const [n, d] of place.doors) {
      const total = (dist.get(n) ?? Infinity) + d;
      if (total < best[0]) best = [total, n];
    }
    return best;
  }

  route(fromQuery, toQuery) {
    const from = asPlace(this, fromQuery);
    const to = asPlace(this, toQuery);
    const { dist, prev } = this.distancesFrom(from);
    const [meters, door] = this.arrival(to, dist);
    if (!isFinite(meters)) throw new Error(`No walking route found from ${from.name} to ${to.name}`);

    const legs = [];
    for (let n = door; prev.has(n); n = prev.get(n)[0]) {
      const [p, edge] = prev.get(n);
      // The slim data shipped inside the Cubbie Skill has no shapes; fall back to the two end points.
      const [a, b, len, name, kind, shape] = this.edges[edge];
      const geom = shape || [this.nodes[a], this.nodes[b]];
      legs.push({ name, kind, len, geom: a === p ? geom : [...geom].reverse() });
    }
    legs.reverse();
    const path = legs.flatMap((l, i) => (i ? l.geom.slice(1) : l.geom));
    return {
      from, to,
      meters: Math.round(meters),
      minutes: Math.max(1, Math.ceil(meters / this.mPerMin)),
      path,
      steps: describe(legs, to.name),
    };
  }

  // Ranks meeting places for a group. Fairness first (the longest anyone walks), then total walking.
  // options.candidates: place ids/names to choose from (default: the map's meeting spots).
  meetup(fromQueries, { candidates, limit = 3 } = {}) {
    const origins = fromQueries.map((q) => asPlace(this, q));
    const dists = origins.map((o) => this.distancesFrom(o).dist);
    const pool = (candidates || this.meta.meeting_spots || this.places).map((q) => asPlace(this, q));
    const ranked = [];
    for (const place of pool) {
      const minutes = dists.map((d) => Math.ceil(this.arrival(place, d)[0] / this.mPerMin));
      if (minutes.some((m) => !isFinite(m))) continue;
      ranked.push({ place, minutes, longest: Math.max(...minutes), total: minutes.reduce((a, b) => a + b, 0) });
    }
    ranked.sort((a, b) => a.longest - b.longest || a.total - b.total);
    return { origins, options: ranked.slice(0, limit) };
  }
}

function asPlace(map, q) {
  if (typeof q === "object") return q;
  const p = map.findPlace(q);
  if (!p) throw new Error(`Unknown place: "${q}"`);
  return p;
}

function norm(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

// Groups the route into a few plain-English steps: "Head north on Cady Mall for 3 min".
function describe(legs, destination) {
  const groups = [];
  for (const leg of legs) {
    const label = leg.name || "the walkway";
    const last = groups[groups.length - 1];
    if (last && (last.label === label || leg.len < 25)) {
      last.len += leg.len;
      last.geom.push(...leg.geom.slice(1));
    } else {
      groups.push({ label, len: leg.len, geom: [...leg.geom] });
    }
  }
  // Fold short stretches into the previous step so a text message stays short.
  const merged = [];
  for (const g of groups) {
    const last = merged[merged.length - 1];
    if (last && (g.len < 60 || g.label === last.label)) {
      last.len += g.len;
      last.geom.push(...g.geom.slice(1));
    } else merged.push(g);
  }
  const steps = merged.map((g, i) => {
    const dir = heading(g.geom[0], g.geom[g.geom.length - 1]);
    const min = Math.max(1, Math.round(g.len / 80));
    const verb = i === 0 ? "Head" : "Continue";
    const along = g.label === "stairs" ? "up/down the stairs" : `on ${g.label}`;
    return `${verb} ${dir} ${along} (${min} min)`;
  });
  steps.push(`Arrive at ${destination}`);
  return steps;
}

function heading([lat1, lon1], [lat2, lon2]) {
  const y = (lon2 - lon1) * Math.cos((lat1 * Math.PI) / 180);
  const deg = (Math.atan2(y, lat2 - lat1) * 180) / Math.PI;
  return ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"][
    Math.round(((deg + 360) % 360) / 45) % 8
  ];
}

class MinHeap {
  constructor() {
    this.items = [];
  }
  get size() {
    return this.items.length;
  }
  push(key, value) {
    const a = this.items;
    a.push([key, value]);
    for (let i = a.length - 1; i > 0; ) {
      const parent = (i - 1) >> 1;
      if (a[parent][0] <= a[i][0]) break;
      [a[parent], a[i]] = [a[i], a[parent]];
      i = parent;
    }
  }
  pop() {
    const a = this.items;
    const top = a[0];
    const end = a.pop();
    if (a.length) {
      a[0] = end;
      for (let i = 0; ; ) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i], a[m]];
        i = m;
      }
    }
    return top;
  }
}
