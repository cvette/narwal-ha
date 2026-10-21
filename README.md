# Narwal Local for Home Assistant

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
settings (volume, do-not-disturb, station automation).

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
| `vacuum.narwal` | state, start (whole home, or resume when paused), pause, stop, return to dock, locate, fan speed (quiet … max), room cleaning with `vacuum.clean_area` |
| `sensor.narwal_battery` | battery % |
| `sensor.narwal_task` | current task (idle, vacuuming, mopping, returning, …) |
| `sensor.narwal_cleaning_progress`, `_cleaned_area`, `_cleaning_time` | updated during a clean |
| `sensor.narwal_current_room` | the room the robot is in, from its live position |
| `sensor.narwal_last_clean`, `_last_clean_area`, `_last_clean_duration` | end time, area and duration of the last finished clean (from the robot's clean report; kept across restarts) |
| `sensor.narwal_maintenance_due`, `_replacement_due` | number of due items, list in attribute `items` |
| `sensor.narwal_error` | the current error in plain words (*Robot stuck*, *Side brush blocked*, *Dirty water tank full or missing*, …); attributes `codes` (hex) and `categories` |
| `sensor.narwal_clean_water_tank`, `_dirty_water_tank`, `_detergent`, `_dust_box`, `_station_dust_bag`, `_dust_bag` | station and robot parts: OK, empty, missing, running low, please empty / replace, fault (only those your robot reports) |
| `binary_sensor.narwal_clean_water_empty`, `_dirty_water_full`, `_detergent_low` | problem sensors for notifications |
| `sensor.narwal_charging_status`, `_error_code` | diagnostics |
| `binary_sensor.narwal_charging`, `_maintenance_needed` | |
| `select.narwal_mop_humidity` | dry / normal / wet |
| `select.narwal_cleaning_mode` | how cleans started from Home Assistant run: vacuum and mop / vacuum / mop / vacuum, then mop |
| `image.narwal_map` | the map: rooms with names, walls, doors, carpets, no-carpet areas, no-go zones, areas the robot cannot enter (darker), and icons for furniture, objects the camera recognised, dirty spots and the dock; during a clean also the robot and its path |
| `event.narwal_clean_finished` | fired when the robot reports the end of a clean: event type `completed`, `stopped` (ended by someone) or `interrupted` (error, low battery, …); attributes `result`, `clean_type`, `area` (m²), `duration` (s), `progress` (%), `start`, `end` |
| `switch.narwal_do_not_disturb`, `time.narwal_do_not_disturb_start`, `_end` | do-not-disturb and its window, in the robot's local time |
| `number.narwal_volume` | voice volume, 0–100 % |
| `switch.narwal_auto_empty`, `_quiet_auto_empty`, `_dust_bag_drying`, `_automatic_detergent`, `_hot_water_mop_wash`, `_child_lock` | station automation and child lock (only those your robot supports) |
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
- **Settings**: writing volume, do-not-disturb and child lock was checked on a
  robot. The station switches use the same `/config/set` call with field
  numbers from the Narwal app, and every change is read back.
- **Discovery** uses the mDNS service the Narwal app looks for
  (`_narwal_sweeper._tcp`). It could not yet be checked on a real network;
  entering the IP address always works.
- One robot per config entry; several robots work as several entries.

## Roadmap

Ideas, not promises: zone cleaning, scheduled cleans, more settings (carpet
handling, corner cleaning), consumable reset.

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

MIT, see [LICENSE](LICENSE).

The map icons are a subset of [Material Design Icons](https://pictogrammers.com/library/mdi/)
(@mdi/font 7.4.47, Apache License 2.0), the icon set Home Assistant uses. See
`custom_components/narwal_local/protocol/assets/NOTICE.md`; the subset is built
by `scripts/build_icon_font.py` (needs `fonttools` and a download of `@mdi/font`).
