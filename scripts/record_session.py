"""Record everything a robot pushes during a session, for protocol work.

Connects read-only, keeps the robot reporting (status, working status and
display map), polls the base status every 15 s, and writes one JSON line per
event. Topics are logged without the /<pid>/<did> prefix. Stop with Ctrl+C.

    python scripts/record_session.py <robot-ip> <out.jsonl> [minutes]
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import conftest  # noqa: E402,F401  (loads the `protocol` package)

from protocol import NarwalRobot  # noqa: E402
from protocol.models import decode_robot_base_status, decode_working_status  # noqa: E402
from protocol.pb import parse  # noqa: E402


def summarize(payload: bytes, depth: int = 0) -> list:
    """Top-level fields: ints as values, bytes as length (+ nested try)."""
    out = []
    try:
        fields = parse(payload)
    except ValueError:
        return [f"<{len(payload)} bytes, not protobuf>"]
    for f in fields:
        if isinstance(f.value, int):
            out.append([f.num, f.value])
        elif f.wtype == 5:
            out.append([f.num, round(f.float, 4)])
        else:
            item = [f.num, f"{len(f.value)}B"]
            if depth < 1 and len(f.value) < 400:
                item.append(summarize(f.value, depth + 1))
            out.append(item)
    return out


def status_view(st) -> dict:
    return {
        "activity": str(st.activity),
        "task": getattr(st.task, "name", st.task),
        "task_status": st.robot_task_status,
        "paused": st.paused,
        "battery": round(st.battery, 1),
        "charging": getattr(st.charging_status, "name", st.charging_status),
        "errors": st.error_codes,
        "fan": getattr(st.fan_level, "name", st.fan_level),
        "mop": getattr(st.mop_humidity, "name", st.mop_humidity),
        "at_origin": st.is_robot_at_origin,
    }


async def main(host: str, out_path: str, minutes: float) -> None:
    out = open(out_path, "a", encoding="utf-8")
    t0 = time.time()

    def log(kind: str, **data) -> None:
        rec = {"t": round(time.time() - t0, 2), "wall": time.strftime("%H:%M:%S"), "kind": kind, **data}
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
        short = {k: v for k, v in data.items() if k not in ("hex", "fields")}
        print(f"[{rec['wall']}] {kind} {json.dumps(short, ensure_ascii=False)[:300]}", flush=True)

    robot = NarwalRobot(host, timeout=30)

    def on_push(msg) -> None:
        topic, payload = msg.topic, msg.payload
        rec = {"topic": topic, "len": len(payload), "hex": payload.hex()}
        try:
            if topic.endswith("robot_base_status"):
                rec["decoded"] = status_view(decode_robot_base_status(payload))
            elif topic.endswith("working_status"):
                rec["decoded"] = asdict(decode_working_status(payload))
            else:
                rec["fields"] = summarize(payload)
        except Exception as err:  # noqa: BLE001 - keep recording whatever arrives
            rec["decode_error"] = repr(err)
        log("push", **rec)

    robot.add_push_callback(on_push)
    robot.add_disconnect_callback(lambda: log("disconnected"))

    deadline = t0 + minutes * 60
    next_keepalive = next_poll = 0.0
    while time.time() < deadline:
        try:
            if not robot.connected:
                await robot.connect()
                log("connected")
                next_keepalive = 0.0
            now = time.time()
            if now >= next_keepalive:
                await robot.activate_reporting(60)
                next_keepalive = now + 45
            if now >= next_poll:
                st = await robot.get_status()
                log("status", decoded=status_view(st))
                next_poll = now + 15
        except Exception as err:  # noqa: BLE001
            log("error", error=repr(err))
            await asyncio.sleep(5)
        await asyncio.sleep(1)
    await robot.close()
    log("done")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 120))
