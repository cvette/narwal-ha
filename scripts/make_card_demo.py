"""Build a stand-alone demo of the map card (dist/card-demo/).

Usage:  python scripts/make_card_demo.py [get_map.bin]

Renders the map payload the integration would send (default: the synthetic
test map), copies the card's JavaScript next to it and writes an index.html
with a stand-in for Home Assistant's `hass` object: the robot drives a loop
through the rooms, and the card's service calls are listed below it. Serve
the folder with any static web server, e.g.
    python -m http.server --directory dist/card-demo 8765
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = ROOT / "custom_components" / "narwal_local" / "protocol"
CARD_JS = ROOT / "custom_components" / "narwal_local" / "www" / "narwal-map-card.js"
OUT = ROOT / "dist" / "card-demo"


def _load_protocol():
    # Loaded by path: the integration folder has select.py and time.py, which
    # would shadow the standard library on sys.path.
    spec = importlib.util.spec_from_file_location(
        "protocol", PROTOCOL / "__init__.py", submodule_search_locations=[str(PROTOCOL)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["protocol"] = module
    spec.loader.exec_module(module)
    return module


PAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Narwal map card demo</title>
<style>
  :root { --primary-color: #0f766e; --text-primary-color: #fff; --primary-text-color: #1f2933;
          --secondary-text-color: #5f6b7a; --divider-color: #d5dbe1; --card-background-color: #fff; }
  @media (prefers-color-scheme: dark) {
    :root { --primary-color: #2dd4bf; --text-primary-color: #06201d; --primary-text-color: #e6eaee;
            --secondary-text-color: #9aa5b1; --divider-color: #39424c; --card-background-color: #1f242a; }
    body { background: #111418 !important; }
  }
  body { margin: 0; padding: 16px; background: #f0f2f5; font-family: system-ui, sans-serif; }
  ha-card { display: block; background: var(--card-background-color); border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,.15); max-width: 560px; }
  pre { max-width: 560px; font-size: 12px; color: var(--secondary-text-color); white-space: pre-wrap; }
</style>
</head>
<body>
<narwal-map-card id="card"></narwal-map-card>
<pre id="log">Service calls:</pre>
<script type="module">
import "./narwal-map-card.js";
const payload = __PAYLOAD__;
const card = document.getElementById("card");
const log = (s) => (document.getElementById("log").textContent += "\\n" + s);
const states = {
  "vacuum.narwal": { entity_id: "vacuum.narwal", state: "docked", attributes: { friendly_name: "Narwal" } },
  "sensor.narwal_battery": { state: "87", attributes: {} },
  "sensor.narwal_position": { state: "0", attributes: {} },
};
// A loop through the middle of every room, starting and ending at the dock.
const dock = payload.dock;
const loop = [dock, ...payload.rooms.map((r) => [(r.bounds[0] + r.bounds[2]) / 2, (r.bounds[1] + r.bounds[3]) / 2]), dock];
let step = 0;
function hass() {
  return {
    states: { ...states },
    locale: { language: "de" },
    entities: { "vacuum.narwal": { entity_id: "vacuum.narwal", platform: "narwal_local" } },
    formatEntityState: (s) => ({ docked: "Angedockt", cleaning: "Reinigt" })[s.state] || s.state,
    callWS: async (msg) => ({ ...payload, path: [], position_entity: "sensor.narwal_position",
                              battery_entity: "sensor.narwal_battery", vacuum_entity: "vacuum.narwal" }),
    callService: async (domain, service, data, target) => {
      log(`${domain}.${service} ${JSON.stringify(data)} ${JSON.stringify(target)}`);
      if (service === "start" || service.startsWith("clean")) states["vacuum.narwal"] = { ...states["vacuum.narwal"], state: "cleaning" };
      if (service === "pause") states["vacuum.narwal"] = { ...states["vacuum.narwal"], state: "paused" };
      if (service === "return_to_base" || service === "stop") states["vacuum.narwal"] = { ...states["vacuum.narwal"], state: "docked" };
      if (service === "add_no_go_zones" || service === "delete_no_go_zones") editNoGo(service, data);
      card.hass = hass();
    },
  };
}
// Applies no-go edits to the demo map the way the robot would (new ids after
// the highest one); the card then fetches the "changed" map again.
function editNoGo(service, data) {
  const t = payload.transform;
  const px = (x, y) => [((x / 1000 - t.origin_x) / t.resolution - t.col0) * t.scale, (t.row1 - (y / 1000 - t.origin_y) / t.resolution) * t.scale];
  const kinds = { no_entry: 3, no_vacuum: 1, no_mop: 2 };
  if (service === "add_no_go_zones") {
    let id = Math.max(0, ...payload.no_go_zones.map((z) => z.id));
    for (const [x1, y1, x2, y2] of data.zones)
      payload.no_go_zones.push({ id: ++id, type: kinds[data.type], points: [px(x1, y1), px(x2, y1), px(x2, y2), px(x1, y2)] });
  } else {
    payload.no_go_zones = payload.no_go_zones.filter((z) => !data.ids.includes(z.id));
  }
  payload.version = String(Date.now());
}
function tick() {
  const cleaning = states["vacuum.narwal"].state === "cleaning";
  const n = 12;  // steps between loop points
  const i = Math.floor(step / n) % (loop.length - 1), f = (step % n) / n;
  const [a, b] = [loop[i], loop[i + 1]];
  const [x, y] = cleaning ? [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f] : dock;
  const heading = cleaning ? (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI : payload.dock_heading;
  states["sensor.narwal_position"] = { state: "0", attributes: { x, y, heading: (heading + 360) % 360 } };
  if (cleaning) step++;
  card.hass = hass();
}
card.setConfig({ entity: "vacuum.narwal" });
tick();
setInterval(tick, 1000);
window.__demo = { states, card, hass };
</script>
</body>
</html>
"""


def main() -> None:
    protocol = _load_protocol()
    from protocol.card import build_map_payload  # noqa: PLC0415

    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "fixtures" / "get_map.bin"
    mi = protocol.decode_get_map_response(source.read_bytes())
    payload = build_map_payload(mi)
    dock = mi.station
    cell = mi.border_point_to_cell(dock.x, dock.y)
    world = mi.cell_to_world(cell.col, cell.row)
    payload["dock"] = [world.x, world.y]
    payload["dock_heading"] = round((dock.theta * 180 / 3.141592653589793) % 360)
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(CARD_JS, OUT / "narwal-map-card.js")
    (OUT / "index.html").write_text(PAGE.replace("__PAYLOAD__", json.dumps(payload)), encoding="utf-8")
    print(f"wrote {OUT / 'index.html'} ({len(payload['rooms'])} rooms, {payload['width']}x{payload['height']} px)")


if __name__ == "__main__":
    main()
