/*
 * Narwal Local map card: the robot's map with its live position and path,
 * tap rooms or draw zones to clean them.
 *
 * Served and registered by the Narwal Local integration; no extra
 * installation. The map comes from the websocket command narwal_local/map,
 * the position from sensor.narwal_position (map metres).
 */

const CARD_VERSION = "1.0.0";

const TEXT = {
  en: {
    rooms: "Rooms",
    zones: "Zones",
    clean: "Clean",
    clear: "Clear",
    repeats: "Passes",
    tapRooms: "Tap rooms to select them.",
    drawZones: "Drag on the map to draw zones (up to 10).",
    nRooms: (n) => `${n} room${n === 1 ? "" : "s"} selected`,
    nZones: (n) => `${n} zone${n === 1 ? "" : "s"}`,
    start: "Start",
    pause: "Pause",
    stop: "Stop",
    dock: "Dock",
    locate: "Locate",
    noEntity: "Choose a Narwal vacuum in the card's settings.",
    loading: "Loading map…",
    started: "Cleaning started.",
  },
  de: {
    rooms: "Räume",
    zones: "Zonen",
    clean: "Reinigen",
    clear: "Leeren",
    repeats: "Durchgänge",
    tapRooms: "Räume antippen, um sie auszuwählen.",
    drawZones: "Auf der Karte ziehen, um Zonen zu zeichnen (bis zu 10).",
    nRooms: (n) => `${n} ${n === 1 ? "Raum" : "Räume"} ausgewählt`,
    nZones: (n) => `${n} ${n === 1 ? "Zone" : "Zonen"}`,
    start: "Start",
    pause: "Pause",
    stop: "Stopp",
    dock: "Station",
    locate: "Finden",
    noEntity: "In den Karteneinstellungen einen Narwal-Sauger wählen.",
    loading: "Karte wird geladen…",
    started: "Reinigung gestartet.",
  },
};

const ACTIVE = new Set(["cleaning", "paused", "returning", "error"]);
const MAX_ZONES = 10;
const POLL_MS = 60000;

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 12px 16px 4px; }
  .title { font-size: 1.1em; font-weight: 500; color: var(--primary-text-color); }
  .status { font-size: 0.9em; color: var(--secondary-text-color); white-space: nowrap; }
  .map { position: relative; margin: 4px 12px; touch-action: none; user-select: none; -webkit-user-select: none; }
  .map img, .map canvas, .map svg { display: block; width: 100%; height: auto; }
  .map canvas, .map svg { position: absolute; inset: 0; height: 100%; }
  .map canvas { image-rendering: pixelated; opacity: 0.45; pointer-events: none; }
  .map.mode-zones { cursor: crosshair; }
  .robot { transition: transform 1s linear; }
  .msg { padding: 24px 16px; color: var(--secondary-text-color); text-align: center; }
  .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 16px; color: var(--primary-text-color); }
  .hint { flex: 1 1 100%; font-size: 0.85em; color: var(--secondary-text-color); min-height: 1.2em; }
  .seg { display: inline-flex; border: 1px solid var(--divider-color); border-radius: 18px; overflow: hidden; }
  .seg button { border: 0; border-radius: 0; }
  button {
    font: inherit; font-size: 0.9em; cursor: pointer; padding: 6px 14px; border-radius: 18px;
    border: 1px solid var(--divider-color); background: var(--card-background-color, #fff);
    color: var(--primary-text-color);
  }
  button.on, button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  button:disabled { opacity: 0.45; cursor: default; }
  select { font: inherit; font-size: 0.9em; padding: 4px; border-radius: 8px; background: var(--card-background-color, #fff); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
  .spacer { flex: 1; }
  .controls { display: flex; gap: 8px; padding: 0 16px 14px; flex-wrap: wrap; }
`;

class NarwalMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._map = null;
    this._mode = "rooms";
    this._rooms = []; // selected room ids, in order
    this._zones = []; // [x1, y1, x2, y2] in image pixels
    this._draft = null;
    this._path = [];
    this._repeats = 1;
    this._lastPos = null;
    this._lastVac = null;
    this._message = "";
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { domain: "vacuum", integration: "narwal_local" } } },
        { name: "title", selector: { text: {} } },
        { name: "show_controls", default: true, selector: { boolean: {} } },
      ],
    };
  }

  static getStubConfig(hass) {
    const entity = Object.values(hass.entities || {}).find(
      (e) => e.platform === "narwal_local" && e.entity_id.startsWith("vacuum."),
    );
    return { entity: entity ? entity.entity_id : "" };
  }

  setConfig(config) {
    this._config = { show_controls: true, ...config };
    this._map = null;
    this._render();
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  connectedCallback() {
    this._timer = setInterval(() => this._load(), POLL_MS);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || (!this._map && !this._loading)) this._load();
    this._update();
  }

  get _t() {
    const lang = (this._hass && this._hass.locale && this._hass.locale.language) || "en";
    return TEXT[lang.split("-")[0]] || TEXT.en;
  }

  // --- data ------------------------------------------------------------------

  async _load() {
    const entity = this._config && this._config.entity;
    if (!this._hass || !entity) return this._render();
    this._loading = true;
    try {
      const res = await this._hass.callWS({
        type: "narwal_local/map",
        entity_id: entity,
        ...(this._map ? { version: this._map.version } : {}),
      });
      this._error = null;
      if (res.image) {
        this._map = res;
        this._grid = Uint8Array.from(atob(res.grid.data), (c) => c.charCodeAt(0));
        this._rooms = this._rooms.filter((id) => res.rooms.some((r) => r.id === id));
        this._render();
      } else if (this._map) {
        Object.assign(this._map, { path: res.path, position_entity: res.position_entity });
      }
      this._path = (res.path || []).map(([x, y]) => this._toPx(x, y));
      this._lastPos = null;
      this._update();
    } catch (err) {
      this._error = err.message || String(err);
      this._render();
    } finally {
      this._loading = false;
    }
  }

  _toPx(x, y) {
    const t = this._map.transform;
    return [((x - t.origin_x) / t.resolution - t.col0) * t.scale, (t.row1 - (y - t.origin_y) / t.resolution) * t.scale];
  }

  _toWorld(px, py) {
    const t = this._map.transform;
    return [t.origin_x + (px / t.scale + t.col0) * t.resolution, t.origin_y + (t.row1 - py / t.scale) * t.resolution];
  }

  _roomAt(px, py) {
    const g = this._map.grid;
    const col = Math.floor(px / this._map.transform.scale);
    const row = Math.floor(py / this._map.transform.scale);
    if (col < 0 || row < 0 || col >= g.width || row >= g.height) return 0;
    return this._grid[row * g.width + col];
  }

  // --- rendering -------------------------------------------------------------

  _render() {
    const t = this._t;
    const cfg = this._config || {};
    const root = this.shadowRoot;
    let body;
    if (!cfg.entity) body = `<div class="msg">${t.noEntity}</div>`;
    else if (this._error) body = `<div class="msg">${escapeHtml(this._error)}</div>`;
    else if (!this._map) body = `<div class="msg">${t.loading}</div>`;
    else body = this._mapHtml();
    root.innerHTML = `<style>${STYLE}</style><ha-card>
      <div class="head"><div class="title"></div><div class="status"></div></div>${body}</ha-card>`;
    if (this._map && !this._error) this._wire();
    this._update();
  }

  _mapHtml() {
    const t = this._t;
    const m = this._map;
    const controls = this._config.show_controls
      ? `<div class="controls">
          <button data-act="start"></button>
          <button data-act="stop">${t.stop}</button>
          <button data-act="dock">${t.dock}</button>
          <button data-act="locate">${t.locate}</button>
        </div>`
      : "";
    return `
      <div class="map mode-${this._mode}">
        <img src="${m.image}" width="${m.width}" height="${m.height}" alt="">
        <canvas width="${m.grid.width}" height="${m.grid.height}"></canvas>
        <svg viewBox="0 0 ${m.width} ${m.height}" preserveAspectRatio="none">
          <polyline class="path" fill="none" stroke="var(--primary-color)" stroke-opacity="0.55"
            stroke-width="3" stroke-linejoin="round" stroke-linecap="round"></polyline>
          <g class="zone-layer"></g>
          <g class="robot" visibility="hidden">
            <circle r="9" fill="var(--primary-color)" stroke="#fff" stroke-width="3"></circle>
            <line x1="0" y1="0" x2="16" y2="0" stroke="#fff" stroke-width="3" stroke-linecap="round"></line>
          </g>
        </svg>
      </div>
      <div class="bar">
        <div class="seg">
          <button data-mode="rooms">${t.rooms}</button><button data-mode="zones">${t.zones}</button>
        </div>
        <span class="spacer"></span>
        <label>${t.repeats} <select class="repeats">
          <option>1</option><option>2</option><option>3</option></select></label>
        <button data-act="clear">${t.clear}</button>
        <button data-act="clean" class="primary">${t.clean}</button>
        <div class="hint"></div>
      </div>${controls}`;
  }

  _wire() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-mode]").forEach((b) =>
      b.addEventListener("click", () => {
        this._mode = b.dataset.mode;
        root.querySelector(".map").className = `map mode-${this._mode}`;
        this._update();
      }),
    );
    root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => this._act(b.dataset.act)));
    const sel = root.querySelector(".repeats");
    sel.value = String(this._repeats);
    sel.addEventListener("change", () => (this._repeats = Number(sel.value)));

    const svg = root.querySelector("svg");
    const point = (ev) => {
      const r = svg.getBoundingClientRect();
      return [((ev.clientX - r.left) * this._map.width) / r.width, ((ev.clientY - r.top) * this._map.height) / r.height];
    };
    svg.addEventListener("pointerdown", (ev) => {
      const [x, y] = point(ev);
      if (this._mode === "rooms") {
        const id = this._roomAt(x, y);
        if (!id) return;
        const i = this._rooms.indexOf(id);
        if (i >= 0) this._rooms.splice(i, 1);
        else this._rooms.push(id);
        this._message = "";
        this._update();
      } else if (this._zones.length < MAX_ZONES) {
        svg.setPointerCapture(ev.pointerId);
        this._draft = [x, y, x, y];
        this._update();
      }
    });
    svg.addEventListener("pointermove", (ev) => {
      if (!this._draft) return;
      const [x, y] = point(ev);
      this._draft[2] = x;
      this._draft[3] = y;
      this._drawZones();
    });
    const finish = () => {
      if (!this._draft) return;
      const [x1, y1, x2, y2] = this._draft;
      this._draft = null;
      if (Math.abs(x2 - x1) > 8 && Math.abs(y2 - y1) > 8) this._zones.push([x1, y1, x2, y2]);
      this._message = "";
      this._update();
    };
    svg.addEventListener("pointerup", finish);
    svg.addEventListener("pointercancel", finish);
  }

  _update() {
    const root = this.shadowRoot;
    const hass = this._hass;
    if (!hass || !root || !this._config) return;
    const t = this._t;
    const vac = hass.states[this._config.entity];
    const title = root.querySelector(".title");
    if (title) title.textContent = this._config.title || (vac && vac.attributes.friendly_name) || "Narwal";
    const status = root.querySelector(".status");
    if (status && vac) {
      const battery = this._map && this._map.battery_entity && hass.states[this._map.battery_entity];
      status.textContent = [hass.formatEntityState ? hass.formatEntityState(vac) : vac.state, battery ? `${battery.state} %` : ""]
        .filter(Boolean)
        .join(" · ");
    }
    if (!this._map) return;

    // Live position and path.
    const pos = this._map.position_entity && hass.states[this._map.position_entity];
    if (vac && this._lastVac && !ACTIVE.has(this._lastVac) && vac.state === "cleaning") this._path = [];
    this._lastVac = vac && vac.state;
    if (pos && pos !== this._lastPos && pos.attributes.x !== undefined) {
      this._lastPos = pos;
      const [px, py] = this._toPx(pos.attributes.x, pos.attributes.y);
      const robot = root.querySelector(".robot");
      if (robot) {
        robot.setAttribute("visibility", "visible");
        robot.style.transform = `translate(${px}px, ${py}px) rotate(${-pos.attributes.heading}deg)`;
      }
      if (vac && ACTIVE.has(vac.state)) {
        const last = this._path[this._path.length - 1];
        if (!last || Math.hypot(last[0] - px, last[1] - py) > 2) this._path.push([px, py]);
      }
    }
    const line = root.querySelector(".path");
    if (line) line.setAttribute("points", this._path.map((p) => p.join(",")).join(" "));

    this._drawSelection();
    this._drawZones();

    root.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("on", b.dataset.mode === this._mode));
    const count = this._mode === "rooms" ? this._rooms.length : this._zones.length;
    const clean = root.querySelector('[data-act="clean"]');
    if (clean) clean.disabled = count === 0;
    const hint = root.querySelector(".hint");
    if (hint) {
      const names = this._rooms.map((id) => (this._map.rooms.find((r) => r.id === id) || {}).name).filter(Boolean);
      hint.textContent =
        this._message ||
        (this._mode === "rooms"
          ? names.length
            ? `${t.nRooms(names.length)}: ${names.join(" → ")}`
            : t.tapRooms
          : this._zones.length
            ? t.nZones(this._zones.length)
            : t.drawZones);
    }
    const start = root.querySelector('[data-act="start"]');
    if (start) start.textContent = vac && vac.state === "cleaning" ? t.pause : t.start;
  }

  _drawSelection() {
    const canvas = this.shadowRoot.querySelector("canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const g = this._map.grid;
    ctx.clearRect(0, 0, g.width, g.height);
    if (this._mode !== "rooms" || !this._rooms.length) return;
    const img = ctx.createImageData(g.width, g.height);
    const color = cssColor(this, "--primary-color", [3, 169, 244]);
    const selected = new Set(this._rooms);
    for (let i = 0; i < this._grid.length; i++) {
      if (!selected.has(this._grid[i])) continue;
      img.data.set([...color, 255], i * 4);
    }
    ctx.putImageData(img, 0, 0);
  }

  _drawZones() {
    const g = this.shadowRoot.querySelector(".zone-layer");
    if (!g) return;
    const rects = this._mode === "zones" ? [...this._zones, ...(this._draft ? [this._draft] : [])] : [];
    g.innerHTML = rects
      .map(([x1, y1, x2, y2], i) => {
        const x = Math.min(x1, x2);
        const y = Math.min(y1, y2);
        return `<rect x="${x}" y="${y}" width="${Math.abs(x2 - x1)}" height="${Math.abs(y2 - y1)}"
          fill="var(--primary-color)" fill-opacity="0.2" stroke="var(--primary-color)" stroke-width="2"
          stroke-dasharray="${i === this._zones.length ? "6 4" : "none"}"></rect>
          <text x="${x + 6}" y="${y + 18}" font-size="16" font-weight="bold" fill="var(--primary-color)">${i + 1}</text>`;
      })
      .join("");
  }

  // --- actions -----------------------------------------------------------------

  async _act(act) {
    const hass = this._hass;
    const entity_id = this._config.entity;
    const vac = hass.states[entity_id];
    try {
      if (act === "clear") {
        if (this._mode === "rooms") this._rooms = [];
        else this._zones = [];
        this._message = "";
      } else if (act === "clean") {
        if (this._mode === "rooms") {
          await hass.callService("narwal_local", "clean_rooms", { rooms: this._rooms, repeats: this._repeats }, { entity_id });
          this._rooms = [];
        } else {
          const zones = this._zones.map(([x1, y1, x2, y2]) =>
            [...this._toWorld(x1, y1), ...this._toWorld(x2, y2)].map((v) => Math.round(v * 1000)),
          );
          await hass.callService("narwal_local", "clean_zone", { zones, repeats: this._repeats }, { entity_id });
          this._zones = [];
        }
        this._message = this._t.started;
      } else if (act === "start") {
        await hass.callService("vacuum", vac && vac.state === "cleaning" ? "pause" : "start", {}, { entity_id });
      } else if (act === "stop") {
        await hass.callService("vacuum", "stop", {}, { entity_id });
      } else if (act === "dock") {
        await hass.callService("vacuum", "return_to_base", {}, { entity_id });
      } else if (act === "locate") {
        await hass.callService("vacuum", "locate", {}, { entity_id });
      }
    } catch (err) {
      this._message = err.message || String(err);
    }
    this._update();
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function cssColor(el, name, fallback) {
  const value = getComputedStyle(el).getPropertyValue(name).trim();
  const probe = document.createElement("canvas").getContext("2d");
  probe.fillStyle = value || `rgb(${fallback.join(",")})`;
  const hex = probe.fillStyle; // normalised to #rrggbb when opaque
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : fallback;
}

if (!customElements.get("narwal-map-card")) {
  customElements.define("narwal-map-card", NarwalMapCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "narwal-map-card",
    name: "Narwal map",
    description: "Live map of a Narwal robot vacuum: tap rooms or draw zones to clean them.",
    preview: false,
    documentationURL: "https://github.com/cvette/narwal-ha#map-card",
  });
  console.info(`%c NARWAL-MAP-CARD %c ${CARD_VERSION} `, "background:#0f766e;color:#fff", "");
}
