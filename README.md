<p align="center">
  <img src="https://raw.githubusercontent.com/cvette/narwal-ha/main/custom_components/narwal_local/brand/icon.png" alt="Narwal Local icon" width="128">
</p>

# Narwal Local for Home Assistant

[![Tests](https://github.com/cvette/narwal-ha/actions/workflows/tests.yml/badge.svg)](https://github.com/cvette/narwal-ha/actions/workflows/tests.yml)
[![Validate](https://github.com/cvette/narwal-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/cvette/narwal-ha/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

Local control of Narwal robot vacuums from Home Assistant, over the robot's own
WebSocket on your network (`ws://<robot-ip>:9002`). No Narwal account, no
cloud, no internet connection needed.

> **Unofficial.** This project is not affiliated with, endorsed by or supported
> by Narwal. The protocol was worked out for interoperability and may change
> with any firmware update. Use it only with a robot you own.

**Status: early.** Tested with one robot on firmware `v01.09.05.04`, including
a recorded full clean. Reading state, the live position and the clean report
work, and so do all commands: start (whole home or chosen rooms), pause/resume,
stop, return to dock, locate, fan speed and mop humidity, plus the robot's
settings (volume, do-not-disturb, station automation) and the station's
actions (empty the dust bin, wash or dry the mop).

What changed in each version: [CHANGELOG.md](CHANGELOG.md).

## Installation (HACS)

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/cvette/narwal-ha` with type **Integration**.
3. Install **Narwal Local** and restart Home Assistant.
4. Home Assistant should offer the robot under **Settings → Devices &
   services → Discovered** (it announces itself over mDNS). Otherwise go to
   **Add integration → Narwal Local** and enter the robot's IP address. Give
   the robot a fixed IP (DHCP reservation) in your router; if it changes,
   discovery updates it, or use **Reconfigure** on the integration.

Manual installation: copy `custom_components/narwal_local` into your Home
Assistant `config/custom_components/` folder and restart.

## Entities

| Entity | Content |
|---|---|
| `vacuum.narwal` | state, start (whole home, or resume when paused), pause, stop, return to dock, locate, fan speed (`mute`, `normal`, `strong`, `deep`, `super`; shown translated), room cleaning with `vacuum.clean_area` |
| `sensor.narwal_battery` | battery % |
| `sensor.narwal_task` | current task (idle, vacuuming, mopping, returning, …) |
| `sensor.narwal_cleaning_progress`, `_cleaned_area`, `_cleaning_time` | updated during a clean |
| `sensor.narwal_current_room` | the room the robot is in, from its live position |
| `sensor.narwal_last_clean`, `_last_clean_area`, `_last_clean_duration` | end time, area and duration of the last finished clean (from the robot's clean report; kept across restarts) |
| `sensor.narwal_maintenance_due`, `_replacement_due` | number of parts due for cleaning / replacement; attributes `items` (keys) and `names` (readable) |
| `sensor.narwal_error` | the current error in plain words (*Robot stuck*, *Side brush blocked*, *Dirty water tank full or missing*, …); attributes `codes` (hex) and `categories` |
| `sensor.narwal_clean_water_tank`, `_dirty_water_tank`, `_detergent`, `_dust_box`, `_station_dust_bag`, `_dust_bag` | station and robot parts: OK, empty, missing, running low, please empty / replace, fault (only those your robot reports) |
| `binary_sensor.narwal_clean_water_empty`, `_dirty_water_full`, `_detergent_low` | problem sensors for notifications |
| `sensor.narwal_charging_status`, `_error_code` | diagnostics |
| `sensor.narwal_battery_health`, `_battery_charge_cycles`, `_battery_capacity`, `_battery_temperature` (`_battery_voltage`, `_battery_current` disabled by default) | battery health, for robots that report it |
| `binary_sensor.narwal_charging`, `_maintenance_needed` | |
| `select.narwal_mop_humidity` | dry / normal / wet |
| `select.narwal_cleaning_mode` | how cleans started from Home Assistant run: vacuum and mop / vacuum / mop / vacuum, then mop |
| `custom:narwal-map-card` | the interactive map card, see *Map card* |
| `image.narwal_map` | the map: rooms with names, walls, doors, carpets, no-carpet areas, no-go zones, areas the robot cannot enter (darker), and icons for furniture, objects the camera recognised, dirty spots and the dock; during a clean also the robot and its path |
| `event.narwal_clean_finished` | fired when the robot reports the end of a clean: event type `completed`, `stopped` (ended by someone) or `interrupted` (error, low battery, …); attributes `result`, `clean_type`, `area` (m²), `duration` (s), `progress` (%), `start`, `end` |
| `switch.narwal_do_not_disturb`, `time.narwal_do_not_disturb_start`, `_end` | do-not-disturb and its window, in the robot's local time |
| `button.narwal_start_plan_…` | one per cleaning plan saved in the Narwal app; starts it (appears within 15 minutes of saving a plan) |
| `button.narwal_empty_dust_bin`, `_wash_mop`, `_dry_mop`, `_wash_and_dry_mop`, `_dry_station_dust_bag` (`_dry_dust_bag` for robots with their own bag) | station actions; the robot must be in the station. Stop one with the vacuum's stop |
| `button.narwal_resume_interrupted_clean` | continues a clean that was interrupted (to recharge, or stopped); unavailable while there is nothing to resume |
| `sensor.narwal_mop_drying_time_left` | remaining mop drying time, 0 when the mop is not drying |
| `select.narwal_map` | the current map, for robots with several (one per floor): choosing one switches the robot to it; unnamed maps show as *Map 1*, *Map 2*, … |
| `select.narwal_ambient_light` | the station's ambient light: off, night light, warm, purple (as far as the station has them) |
| `number.narwal_volume` | voice volume, 0–100 % |
| `switch.narwal_auto_empty`, `_quiet_auto_empty`, `_dust_bag_drying`, `_automatic_detergent`, `_hot_water_mop_wash`, `_child_lock` | station automation and child lock (only those your robot supports) |
| `switch.narwal_deep_clean_heavy_dirt`, `_pet_mode`, `_carpets_first`, `_deep_carpet_cleaning`, `_station_light` | more cleaning settings (only those your robot has) |
| `select.narwal_carpets` | on carpets: clean with more suction, cross without cleaning, treat as floor, avoid |
| `select.narwal_mop_drying`, `_mop_washing`, `_corner_cleaning`, `_obstacle_avoidance` | mop drying strength, how often the mop is washed, corner cleaning, obstacle avoidance |
| `sensor.narwal_detected_obstacles` | number of objects the camera recognised on the floor (cables, shoes, socks, pet waste, …); list in attribute `obstacles` |
| `sensor.narwal_last_detected` | what was recognised, as text: `3× Cable, 2× Shoes, 1× Plastic bag` (in German: `3× Kabel, 2× Schuhe, 1× Plastiktüte`) |

The map image has these attributes:

| Attribute | Content |
|---|---|
| `rooms` | room ids and names |
| `dock_room` | room the dock stands in |
| `furniture` | furniture with `type` (`double_bed`, `sofa_l_shape`, `toilet`, …), display `name` and `room` |
| `obstacles` | recognised objects with `type` (`cable`, `shoes`, `poop`, …), display `name` and `room` |
| `dirt` | recognised dirty spots with `type`, `name`, `status` (`exploring`, `cleaning`, `cleaned`) and `room` |

`type` is a stable English key for automations; `name` follows Home
Assistant's language (English and German included). The names live in the
`selector` section of the translations, generated by `scripts/object_names.py`.

The map is re-read every 15 minutes and re-rendered only when something on it
changed. Recognised objects reflect the robot's last clean (the robot clears
them when a new clean starts). While the robot is cleaning, paused or returning,
the image shows it live with the path of the current clean, refreshed at most
every 5 seconds; the base map is rendered once per map version, so a refresh
costs only a few tens of milliseconds. Show the map on a dashboard with a
*Picture entity* card.

Example automation trigger for pet waste:

```yaml
trigger:
  - platform: template
    value_template: >
      {{ state_attr('sensor.narwal_detected_obstacles', 'obstacles')
         | selectattr('type', 'eq', 'poop') | list | count > 0 }}
```

Updates are pushed by the robot. The integration re-arms the robot's reporting
every 45 s and polls every 60 s as a fallback. The robot drops the connection
now and then (a few times per clean); the integration reconnects at once and
only marks the entities unavailable if that fails. Diagnostics can be downloaded
from the device page (device token and ids are redacted).

Example automation when a clean has finished:

```yaml
trigger:
  - platform: state
    entity_id: event.narwal_clean_finished
condition:
  - condition: state
    entity_id: event.narwal_clean_finished
    attribute: event_type
    state: completed
action:
  - action: notify.mobile_app_phone
    data:
      message: >
        Cleaned {{ state_attr('event.narwal_clean_finished', 'area') }} m² in
        {{ (state_attr('event.narwal_clean_finished', 'duration') / 60) | round }} min.
```

Settings are read from the robot every 60 s, so changes made in the Narwal app
show up in Home Assistant too. After a change from Home Assistant the settings
are read back at once, so the entities show what the robot stored.

## Map card

The integration brings its own dashboard card; there is nothing extra to
install. Edit a dashboard, **Add card**, and pick **Narwal map** (or use the
YAML below). The card shows the map with the robot moving live and the path
of the current clean, and lets you

- tap rooms (in the order to clean them) and start a clean of just those,
- switch to **Zones**, drag up to 10 rectangles on the map and clean them,
- add no-go zones (**Sperrzonen**/**No-go**) by dragging, or tap existing ones to
  delete them, then save,
- choose 1 to 3 passes, and start, pause, stop, dock or locate the robot.

```yaml
type: custom:narwal-map-card
entity: vacuum.narwal
title: Narwal          # optional
show_controls: true    # optional: the start / stop / dock / locate row
```

The card follows your theme and Home Assistant's language (English and
German). After an update of the integration, reload the browser page once if
the card still looks old. Room cleaning from the card uses the action
`narwal_local.clean_rooms` (room ids, as listed by the map image), which
works in scripts too.

## Zone cleaning

`narwal_local.clean_zone` cleans rectangles, in the given order, with the
current suction, mop humidity and `select.narwal_cleaning_mode` (verified on a
robot). Each zone is
`[x1, y1, x2, y2]`: two opposite corners in millimetres in the map's frame.

```yaml
action: narwal_local.clean_zone
target:
  entity_id: vacuum.narwal
data:
  zones:
    - [1200, 3400, 2800, 5000]
  repeats: 1
```

To find coordinates, use `image.narwal_map`'s attribute `calibration_points`:
three corners of the image with their position on the map, the format map
cards use to turn a drawn rectangle into these numbers. An example for the
[Xiaomi Vacuum Map Card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card)
(not tested yet; check the card's documentation if it does not draw):

```yaml
type: custom:xiaomi-vacuum-map-card
entity: vacuum.narwal
map_source:
  camera: image.narwal_map
calibration_source:
  entity: image.narwal_map
  attribute: calibration_points
map_modes:
  - name: Clean zones
    icon: mdi:selection-drag
    selection_type: MANUAL_RECTANGLE
    coordinates_rounding: true
    max_selections: 10
    repeats_type: EXTERNAL
    max_repeats: 3
    service_call_schema:
      service: narwal_local.clean_zone
      service_data:
        entity_id: "[[entity_id]]"
        zones: "[[selection]]"
        repeats: "[[repeats]]"
```

## No-go zones

Areas the robot must not enter, vacuum or mop, the same ones the Narwal app
edits. `image.narwal_map` lists them in `no_go_zones` with their id, type
(`no_entry`, `no_vacuum`, `no_mop`) and bounds in millimetres.

```yaml
action: narwal_local.add_no_go_zones
target:
  entity_id: vacuum.narwal
data:
  zones:
    - [1200, 3400, 2000, 4000]
  type: no_entry      # or no_vacuum / no_mop
```

`narwal_local.delete_no_go_zones` deletes zones by `ids`, or all of them
without ids. The map card does both in its no-go mode.

## Position and floor plan

`sensor.narwal_position` shows the robot's distance from the dock, and its
attributes say where it is: `x`, `y` in metres (the frame of `clean_zone` and
`calibration_points`), `heading` in degrees and `room`. While the robot moves
it updates at most once a second; in the dock it shows the dock's position.
The position attributes are not stored in the history; exclude the whole
sensor from the recorder if you do not want its state rows either.

To place the robot on your own floor plan, open the integration's
**Configure** dialog and enter three spots you can find on both maps: their
map position in metres and the same spot on your floor plan, in percent of
the image or in pixels. Room corners work well: `image.narwal_map` lists each
room's `bounds` (`[x_min, y_min, x_max, y_max]` in metres). Rotation, scale and
mirroring are worked out from the three points. The sensor then also has
`floorplan_x`, `floorplan_y` and `floorplan_heading` (degrees, clockwise with
the image's y axis pointing down).

Example with a Picture Elements card and
[card-mod](https://github.com/thomasloven/lovelace-card-mod), with the
calibration entered in percent (not tested on every setup):

```yaml
type: picture-elements
image: /local/floorplan.png
elements:
  - type: icon
    icon: mdi:robot-vacuum
    entity: vacuum.narwal
    style:
      left: 0%
      top: 0%
    card_mod:
      style: |
        :host {
          left: {{ state_attr('sensor.narwal_position', 'floorplan_x') }}% !important;
          top: {{ state_attr('sensor.narwal_position', 'floorplan_y') }}% !important;
        }
```

`sensor.narwal_current_room` works without any calibration, for example to
highlight the robot's room on a floor plan or in a 3D view.

## Consumables

The robot itself only knows which parts are due (shown by
`sensor.narwal_maintenance_due` and `_replacement_due`). After cleaning or
replacing a part, clear its reminder with the action
`narwal_local.reset_consumables`:

```yaml
action: narwal_local.reset_consumables
data:
  config_entry_id: <your robot's entry>   # pick the robot in the UI editor
  items:
    - station_bag
```

Without `items`, every due reminder is cleared. Remaining-life percentages
are not available: the Narwal app gets them from Narwal's cloud, and resetting
here does not change them in the app.

## Room cleaning

The robot's rooms are offered to Home Assistant's area cleaning: open the
vacuum entity's settings, choose **Map vacuum segments to areas** and assign
each robot room (Living room, Kitchen, …) to one of your Home Assistant areas.
Then clean areas from the vacuum card, voice assistants or automations:

```yaml
action: vacuum.clean_area
target:
  entity_id: vacuum.narwal
data:
  cleaning_area_id:
    - kitchen
    - hallway
```

Rooms are cleaned in the order given, with the robot's current fan speed and
mop humidity and the mode from `select.narwal_cleaning_mode`. If rooms change
in the app (renamed, split, merged), Home Assistant shows a repair asking you
to update the mapping.

Error codes are grouped into about 30 categories with this project's own
wording. The code table comes from the Narwal app, which ships it for one
model (J4); codes follow the firmware modules and are largely shared between
models. A code that is not in the table shows as *Unknown error* with the code
in the `codes` attribute.

## Limitations

- **Whole-home cleans** are sent as "every room of the current map" (the robot
  accepts but ignores a whole-map request).
- **Vacuum state** is derived from the robot's task status. *Docked*,
  *cleaning*, *paused* and *returning* are verified on a recorded clean;
  *error* still needs confirmation on a robot.
- **Remaining time** is not reported by the robot, so there is no sensor for it.
- **Camera / live video** is not supported: it is brokered through Narwal's
  cloud.
- **Photos of detected objects** are not shown, by design. The robot uploads
  them encrypted to Narwal's cloud storage and reports only their URL locally;
  the decryption key is handed out by Narwal's cloud after an account login.
  The integration stays fully local and shows each object's type, icon and
  room instead.
- **Settings**: writing volume, do-not-disturb, child lock, station light,
  carpets first and mop drying was checked on a robot. The others use the
  same `/config/set` call with field numbers from the Narwal app, and every
  change is read back.
- **Sending the robot to a point** is not offered: the app does it only in
  its live video view, and without a video session the robot drops the
  connection and restarts its control software (seen twice).
- **Firmware updates** are offered by Narwal's cloud: the robot only learns
  the new version from the app, so Home Assistant cannot show or install
  them.
- **Schedules** cannot be read or changed locally: the Narwal app keeps
  them in Narwal's cloud. Use Home Assistant automations with
  `vacuum.clean_area` instead; they run without the cloud.
- **Consumable lifetimes** (percentages) live in Narwal's cloud too; see
  *Consumables*.
- **Station buttons**: dry mop is verified on a robot (and ending it with
  stop); the others use the Narwal app's own station commands but have not
  been pressed on a robot yet.
- **Discovery** uses the mDNS service the Narwal app looks for
  (`_narwal_sweeper._tcp`). It could not yet be checked on a real network;
  entering the IP address always works.
- One robot per config entry; several robots work as several entries.

## Roadmap

Ideas, not promises: editing no-go zones from Home Assistant, more robot
models confirmed by users.

## Development

`custom_components/narwal_local/protocol/` is a self-contained async client for
the robot (only `aiohttp`), independent of Home Assistant:

| Module | Content |
|---|---|
| `pb.py` | minimal protobuf reader/writer |
| `frame.py` | frame `0x01 + varint(len) + Header + payload`, Header message |
| `client.py` | `NarwalClient` (connect, call, pushes) and `NarwalRobot` (typed calls) |
| `models.py` | status, working status, device info, features, consumables, firmware, clean report |
| `config.py` | settings: `/config/get` and `/config/set` (whose field numbers differ from the read side) |
| `map.py` | `/map/get_map` decoding: grid, rooms, doors, carpets, forbidden zones |
| `render.py` | map → PNG with the standard library; icons, labels, robot and path with Pillow (`MapRenderer` caches per map) |

### Error codes

`scripts/build_error_codes.py <en-US.json>` rebuilds
`protocol/assets/errors.json` (code → category) from an error table of the
decompiled app. Only the mapping is stored; the texts are in the translations.

### Recording a session

`scripts/record_session.py <robot-ip> <out.jsonl> [minutes]` connects
read-only, keeps the robot reporting and writes every push (status, working
status, live position, clean report, …) plus a status poll every 15 s as JSON
lines. Start it before a clean to see what the robot sends; topics are logged
without the product and device id. Recordings contain your map and positions,
so keep them out of the repository (`dist/` is ignored).

### Tests

Protocol tests run on any OS; the Home Assistant tests are skipped when Home
Assistant is not installed:

```bash
python -m venv .venv
.venv/bin/pip install aiohttp pytest pytest-asyncio   # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest
NARWAL_HOST=192.168.1.113 .venv/bin/python -m pytest -m live   # read-only, real robot
```

The full suite needs Linux (Home Assistant does not run natively on Windows;
use WSL there):

```bash
bash scripts/test-ha.sh
```

It creates a Python 3.14 venv with `pytest-homeassistant-custom-component` in
`~/narwal-ha-venv` on first run. CI runs the same suite plus HACS and hassfest
validation.

`tests/fixtures/` holds robot payloads captured read-only (`*.bin`) and an
independent decoder's output for the same bytes (`*.json`) as golden data. The
device token, device id, product id and account binding id are replaced by
same-length dummies. The map fixture is synthetic
(`scripts/make_synthetic_map.py`): real structure, invented floor plan.

## License

MIT, see [LICENSE](LICENSE). The icon (`assets/logo/icon.svg`) is original
artwork for this project under the same licence; it is not a Narwal logo.

The map icons are a subset of [Material Design Icons](https://pictogrammers.com/library/mdi/)
(@mdi/font 7.4.47, Apache License 2.0), the icon set Home Assistant uses. See
`custom_components/narwal_local/protocol/assets/NOTICE.md`; the subset is built
by `scripts/build_icon_font.py` (needs `fonttools` and a download of `@mdi/font`).
