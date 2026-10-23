# Changelog

All notable changes to Narwal Local. Versions follow the `version` in
`custom_components/narwal_local/manifest.json`; each release on GitHub is
built from the tag of the same name. "Verified" means checked on a real
robot.

## 0.12.0 – 2026-10-24

- `sensor.narwal_last_event` from the robot's cleaning timeline (polled
  and pushed during tasks), with the last events and their rooms.
- `select.narwal_voice_language` for the robot's voice language, verified
  (the robot answers "failed" even when it switched, so the language is
  read back instead).
- `button.narwal_restart` restarts the robot's software, verified: it is back
  after about 50 seconds and the integration reconnects.
- Fix: a failed connect in `async with NarwalRobot(...)` now closes the
  client's own HTTP session.
- `select.narwal_map`: switch between the robot's maps (floors), read
  with `/map/get_all_reduced_maps` (verified read-only on a robot with one
  map; switching not yet tried).
- More station buttons: wash and dry mop, dry the station's dust bag (and
  the robot's own bag where it has one).
- `button.narwal_resume_interrupted_clean`: continue an interrupted clean.
- `sensor.narwal_mop_drying_time_left` (seconds, verified: a drying run
  starts at 5 hours).
- `select.narwal_ambient_light` for the station's ambient light, verified.
- Verified on a robot: the dry mop button and ending the drying with stop.
- Battery health sensors (diagnostic): health, charge cycles, full-charge
  capacity, temperature; voltage and current are disabled by default.

## 0.11.0 – 2026-10-23

- No-go zones: actions `narwal_local.add_no_go_zones` (no entry, no
  vacuuming or no mopping) and `narwal_local.delete_no_go_zones`, sent as a
  map edit like the app's, verified on a robot; `image.narwal_map` lists the
  zones with ids.
- Map card: a no-go mode to draw new zones and tap existing ones to delete
  them.
- Fix: existing no-go zones (and virtual walls) were read as metres; they
  are map cells like furniture, so maps with no-go zones showed them in the
  wrong place.

## 0.10.0 – 2026-10-23

- Map card `custom:narwal-map-card`, served and registered by the
  integration: live robot and path, tap rooms or draw zones to clean them,
  passes, and start / pause / stop / dock / locate. Data comes over the
  websocket command `narwal_local/map`.
- Action `narwal_local.clean_rooms`: clean rooms by id, in order, with 1 to 3
  passes.
- Zone cleaning, verified: action `narwal_local.clean_zone` cleans rectangles
  given in millimetres; `image.narwal_map` gains `calibration_points`, so map cards
  can turn a drawn rectangle into a zone.
- A start button for each cleaning plan saved in the Narwal app (not yet
  tried on a robot).
- `sensor.narwal_position`: distance from the dock, with the position in
  metres, heading and room as attributes; updates at most once a second
  while the robot moves.
- Floor plan calibration in the integration's options: three reference
  points turn the position into `floorplan_x` / `floorplan_y` on your own
  floor plan. The map image lists each room's bounds in metres.
- The icon at the top of the README, and a social preview card for links to
  the repository (`assets/logo/social-preview.png`).

## 0.9.1 – 2026-10-23

- The integration ships its own icon (`brand/icon.png`, `icon@2x.png`),
  shown by Home Assistant 2026.3 and later. Original artwork, MIT licence,
  without Narwal or Home Assistant marks.
- The HACS check runs without ignores.

## 0.9.0 – 2026-10-22

- Settings as selects: carpets (more suction, cross without cleaning, treat
  as floor, avoid), mop drying, how often the mop is washed, corner
  cleaning, obstacle avoidance.
- Settings as switches: deep clean of heavy dirt, pet mode, carpets first,
  deep carpet cleaning, station light. Only settings the robot reports and
  supports get an entity. Writing station light, carpets first and mop
  drying is verified.
- Action `narwal_local.reset_consumables` clears the robot's reminders for
  parts that are due. The due-part sensors gain readable `names`.
- Not possible locally, documented in the README: schedules and
  remaining-life percentages, which the Narwal app keeps in Narwal's cloud.

## 0.8.0 – 2026-10-22

- Station buttons: empty dust bin, wash mop, dry mop (created when the robot
  has a station).
- Icons for the new buttons and the settings entities.
- Clearer German name for automatic detergent.
- CI: read-only token permissions, pip cache, status badges in the README.

## 0.7.0 – 2026-10-21

- Settings: volume, do-not-disturb with start and end time, auto-empty,
  quiet auto-empty, dust bag drying, automatic detergent, hot water mop
  wash, child lock. Every change is read back from the robot; volume,
  do-not-disturb and child lock are verified.
- `event.narwal_clean_finished`: completed, stopped or interrupted, with
  result, clean type, area, duration and times.
- Discovery over mDNS (`_narwal_sweeper._tcp`); a known robot gets its new
  address.

## 0.6.0 – 2026-10-21

- Station sensors: clean water tank, dirty water tank, detergent, dust box,
  station dust bag, robot dust bag; problem binary sensors for clean water
  empty, dirty water full and detergent low.
- `sensor.narwal_error`: the current error as one of about 30 categories
  in plain English or German, with the codes in the attributes.

## 0.5.0 – 2026-10-21

- Start (whole home, or resume when paused), stop and locate from
  Home Assistant, verified.
- Room cleaning with `vacuum.clean_area`, rooms cleaned in the given order;
  a repair appears when the robot's rooms change.
- `select.narwal_cleaning_mode` for cleans started from Home Assistant.

## 0.4.0 – 2026-10-21

- The robot live on the map with the path of the current clean; areas it
  cannot enter shown darker. Live frames are cached and throttled.
- `sensor.narwal_current_room` from the live position.
- Last clean end, area and duration from the robot's clean report, kept
  across restarts.
- Quiet reconnects when the robot drops the connection; dust emptying and
  charging count as docked. The remaining-time sensor is removed (the robot
  never reports it).

## 0.3.1 – 2026-10-21

- Room lookups use a cached room grid: state updates no longer take half a
  second.

## 0.3.0 – 2026-10-21

- Icons on the map for detected objects, furniture, dirty spots and the dock
  (a subset of Material Design Icons, Apache 2.0).
- English and German names for all object types; `sensor.narwal_last_detected`.

## 0.2.0 – 2026-10-20

- `image.narwal_map`: rooms, walls, doors, carpets, no-go zones, furniture,
  detected objects, dirty spots and the dock.
- `sensor.narwal_detected_obstacles`.

## 0.1.0 – 2026-10-20

- First version: local connection to the robot's WebSocket, config flow,
  vacuum entity, status sensors, mop humidity select, diagnostics.
