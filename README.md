# Narwal Local for Home Assistant

Local control of Narwal robot vacuums from Home Assistant, over the robot's own
WebSocket on your network (`ws://<robot-ip>:9002`). No Narwal account, no
cloud, no internet connection needed.

> **Unofficial.** This project is not affiliated with, endorsed by or supported
> by Narwal. The protocol was worked out for interoperability and may change
> with any firmware update. Use it only with a robot you own.

**Status: early.** Tested with one robot on firmware `v01.09.05.04`. Reading
state works; of the commands, return to dock, pause/resume, fan speed and mop
humidity are verified. Starting a clean is not supported yet (see
[Roadmap](#roadmap)).

## Installation (HACS)

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/cvette/narwal-ha` with type **Integration**.
3. Install **Narwal Local** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → Narwal Local** and
   enter the robot's IP address. Give the robot a fixed IP (DHCP reservation)
   in your router; if it changes, use **Reconfigure** on the integration.

Manual installation: copy `custom_components/narwal_local` into your Home
Assistant `config/custom_components/` folder and restart.

## Entities

| Entity | Content |
|---|---|
| `vacuum.narwal` | state, pause, return to dock, fan speed (quiet … max); *start* resumes a paused clean |
| `sensor.narwal_battery` | battery % |
| `sensor.narwal_task` | current task (idle, vacuuming, mopping, returning, …) |
| `sensor.narwal_cleaning_progress`, `_cleaned_area`, `_cleaning_time`, `_remaining_time`, `_current_room` | updated during a clean |
| `sensor.narwal_maintenance_due`, `_replacement_due` | number of due items, list in attribute `items` |
| `sensor.narwal_charging_status`, `_error_code` | diagnostics |
| `binary_sensor.narwal_charging`, `_maintenance_needed` | |
| `select.narwal_mop_humidity` | dry / normal / wet |

Updates are pushed by the robot. The integration re-arms the robot's reporting
every 45 s and polls every 60 s as a fallback; if the connection drops it
reconnects on its own. Diagnostics can be downloaded from the device page
(device token and ids are redacted).

## Limitations

- **Starting a new clean, room cleaning, stop and locate** are not available
  yet; they are mapped out but not verified on a robot.
- **Vacuum state** is derived from the robot's task status using the app's
  enum names. *Docked* is verified; *cleaning*, *returning*, *paused* and
  *error* still need confirmation on a running robot.
- **Camera / live video** is not supported: it is brokered through Narwal's
  cloud.
- One robot per config entry; several robots work as several entries.

## Roadmap

1. Verify start, room cleaning, stop and locate on a robot.
2. Room cleaning through Home Assistant's `vacuum.clean_area` (map robot rooms
   to Home Assistant areas).
3. The map as an `image` entity (rooms, doors, carpets, no-go zones; the
   renderer already exists in `protocol/render.py`).
4. Live robot position on the map.

## Development

`custom_components/narwal_local/protocol/` is a self-contained async client for
the robot (only `aiohttp`), independent of Home Assistant:

| Module | Content |
|---|---|
| `pb.py` | minimal protobuf reader/writer |
| `frame.py` | frame `0x01 + varint(len) + Header + payload`, Header message |
| `client.py` | `NarwalClient` (connect, call, pushes) and `NarwalRobot` (typed calls) |
| `models.py` | status, working status, device info, features, consumables, firmware |
| `map.py` | `/map/get_map` decoding: grid, rooms, doors, carpets, forbidden zones |
| `render.py` | map → PNG with the standard library only |

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
