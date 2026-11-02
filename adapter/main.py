"""Host-side LinuxCNC bridge. Python stdlib only; run with system Python."""
import argparse
import asyncio
import json
import math
import signal
from pathlib import Path
import stat
import time

AXES = {"X": 0, "Y": 1, "U": 6, "V": 7}
MASK = sum(1 << i for i in AXES.values())

class Controller:
    def __init__(self, api, program_dir, max_jog=5.0):
        self.api = api
        self.status = api.stat()
        self.command = api.command()
        self.errors = api.error_channel()
        self.program_dir = Path(program_dir).resolve()
        self.max_jog = max_jog
        self.owner = None
        self.deadline = 0.0
        self.active = set()
        self.latest_error = None
        self.mdi_pending_serial = None

    def poll(self):
        self.status.poll()
        if self.status.axis_mask != MASK:
            raise ValueError("Expected exactly XYUV axes")
        if self.status.joints != 4:
            raise ValueError("Expected four joints: X,Y,U,V")
        if (self.mdi_pending_serial is not None and
                self.status.echo_serial_number >= self.mdi_pending_serial and
                self.status.interp_state == self.api.INTERP_IDLE):
            self.mdi_pending_serial = None
        return self.status

    def stop(self):
        # Attempt every axis even if one LinuxCNC command fails.
        failure = None
        for index in AXES.values():
            try:
                self.command.jog(self.api.JOG_STOP, False, index)
            except Exception as exc:
                failure = exc
        self.active.clear()
        self.owner = None
        self.deadline = 0.0
        if failure:
            raise failure

    def expire(self):
        if self.active and time.monotonic() >= self.deadline:
            self.stop()

    def snapshot(self):
        s = self.poll()
        error = self.errors.poll()
        if error:
            self.latest_error = {"kind": error[0], "message": error[1]}
        # Use coordinate positions, never joint positions, for axis offsets.
        machine = {a: s.actual_position[i] for a, i in AXES.items()}
        work = {a: machine[a] - s.g5x_offset[i] - s.tool_offset[i]
                for a, i in AXES.items()}
        theta = math.radians(-s.rotation_xy)
        x, y = work["X"], work["Y"]
        work["X"] = x * math.cos(theta) - y * math.sin(theta)
        work["Y"] = x * math.sin(theta) + y * math.cos(theta)
        work = {a: work[a] - s.g92_offset[i] for a, i in AXES.items()}
        return {"axes": list(AXES), "machine": machine, "work": work,
                "joint_positions": list(s.joint_actual_position)[:4],
                "homed": list(s.homed)[:4],
                "homing": [bool(j.get("homing", False)) for j in getattr(s, "joint", ())[:4]],
                "estop": bool(s.estop),
                "enabled": bool(s.enabled), "task_mode": s.task_mode,
                "interp_state": s.interp_state, "paused": bool(s.paused),
                "line": s.motion_line, "file": s.file, "mdi_pending": self.mdi_pending_serial is not None,
                "error": self.latest_error, "sample_monotonic": time.monotonic()}

    def execute(self, msg):
        cmd = msg.get("cmd")
        owner = msg.get("session")
        if not isinstance(owner, str) or not 1 <= len(owner) <= 80:
            raise ValueError("Missing session")
        if cmd == "status":
            return self.snapshot()
        if cmd in ("stop", "abort", "estop"):
            if cmd == "estop":
                self.command.state(self.api.STATE_ESTOP)
            elif cmd == "abort":
                self.command.abort()
            try:
                self.stop()
            except Exception:
                if cmd == "stop":
                    raise
            return {}
        if cmd == "release":
            if owner == self.owner:
                self.stop()
            return {}
        s = self.poll()
        if cmd == "reset_estop":
            self.command.state(self.api.STATE_ESTOP_RESET)
            return {}
        if cmd == "disable":
            self.command.state(self.api.STATE_OFF)
            try:
                self.stop()
            except Exception:
                pass
            return {}
        if s.estop:
            raise ValueError("Machine is in ESTOP")
        if cmd == "enable":
            if s.interp_state != self.api.INTERP_IDLE or self.active:
                raise ValueError("Machine must be idle")
            self.command.state(self.api.STATE_ON)
            return {}
        if not s.enabled:
            raise ValueError("Machine is disabled")
        if cmd in ("mdi_mode", "mdi"):
            if (s.interp_state != self.api.INTERP_IDLE or s.paused or self.active or
                    any(j.get("homing", False) for j in getattr(s, "joint", ())) or
                    self.mdi_pending_serial is not None):
                raise ValueError("Machine must be idle")
            if len(s.homed) < 4 or not all(s.homed[:4]):
                raise ValueError("Home all four joints before MDI")
            if cmd == "mdi_mode":
                self.command.mode(self.api.MODE_MDI)
                return {}
            if s.task_mode != self.api.MODE_MDI:
                raise ValueError("Select MDI mode and wait for status confirmation")
            text = msg.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("MDI requires one nonempty line")
            if len(text.encode("utf-8")) > 254 or any(ord(c) < 32 or ord(c) > 126 for c in text):
                raise ValueError("MDI must be one ASCII line, at most 254 bytes")
            self.command.mdi(text.strip())
            self.mdi_pending_serial = self.command.serial
            return {}
        if cmd in ("home_all", "home_axis", "jog"):
            if s.task_mode != self.api.MODE_MANUAL or s.interp_state != self.api.INTERP_IDLE:
                raise ValueError("Select MANUAL and idle first")
        if cmd in ("home_all", "home_axis"):
            if (self.mdi_pending_serial is not None or s.paused or
                    any(j.get("homing", False) for j in getattr(s, "joint", ()))):
                raise ValueError("Wait until machine and homing are idle")
            axis = msg.get("axis")
            if cmd == "home_axis" and axis not in AXES:
                raise ValueError("Axis must be X,Y,U,V")
            if self.active:
                raise ValueError("Stop jogging first")
            self.command.teleop_enable(False)
            self.command.home(-1 if cmd == "home_all" else list(AXES).index(axis))
        elif cmd == "manual":
            if s.interp_state != self.api.INTERP_IDLE or self.active:
                raise ValueError("Machine must be idle")
            self.command.mode(self.api.MODE_MANUAL)
        elif cmd == "jog":
            if not all(s.homed[:4]):
                raise ValueError("Home all joints first")
            if s.motion_mode != self.api.TRAJ_MODE_TELEOP:
                raise ValueError("Enable world mode first")
            if self.owner not in (None, owner):
                raise ValueError("Another client owns jogging")
            axis = msg.get("axis")
            if axis not in AXES:
                raise ValueError("Axis must be X,Y,U,V")
            velocity = msg.get("velocity")
            if isinstance(velocity, bool) or not isinstance(velocity, (int, float)):
                raise ValueError("Invalid velocity")
            if not math.isfinite(velocity) or velocity == 0 or abs(velocity) > self.max_jog:
                raise ValueError("Velocity exceeds adapter limit")
            # Lease is renewed only by a fresh jog command; no generic heartbeat.
            # One axis per session in this initial implementation.
            if self.active and axis not in self.active:
                self.stop()
            self.owner = owner
            self.deadline = time.monotonic() + 0.4
            self.active.add(axis)
            self.command.jog(self.api.JOG_CONTINUOUS, False, AXES[axis], velocity)
        elif cmd == "world":
            if self.active or not all(s.homed[:4]) or s.interp_state != self.api.INTERP_IDLE:
                raise ValueError("Must be homed and idle")
            if s.task_mode != self.api.MODE_MANUAL:
                raise ValueError("Select MANUAL first")
            self.command.teleop_enable(True)
        elif cmd == "pause":
            self.command.auto(self.api.AUTO_PAUSE)
        else:
            raise ValueError("Unsupported command")
        return {}

async def serve(controller, socket_path):
    main_task = asyncio.current_task()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, main_task.cancel)
    path = Path(socket_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Do not unlink another live server's socket.
        try:
            reader, writer = await asyncio.open_unix_connection(str(path))
        except ConnectionRefusedError:
            if not stat.S_ISSOCK(path.lstat().st_mode):
                raise RuntimeError("Socket path is not a socket")
            path.unlink()
        else:
            writer.close()
            await writer.wait_closed()
            raise RuntimeError("Adapter already running")

    preview_busy = False
    async def client(reader, writer):
        nonlocal preview_busy
        is_preview = False
        try:
            line = await asyncio.wait_for(reader.readline(), 1.0)
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError("Expected object")
            controller.expire()
            is_preview = msg.get("cmd") == "preview"
            if is_preview:
                from adapter.preview import context_for, generate
                if preview_busy:
                    raise ValueError("Another preview is running")
                status = controller.poll()
                if controller.active or status.interp_state != controller.api.INTERP_IDLE:
                    raise ValueError("Preview requires an idle machine")
                context = context_for(status, msg.get("text"))
                preview_busy = True
                try:
                    reply = await generate(context)
                finally:
                    preview_busy = False
            else:
                result = controller.execute(msg)
                reply = {"ok": True, "data": result}
        except Exception as exc:
            # Any failed request during a jog terminates its lease.
            try:
                if not is_preview:
                    controller.stop()
            except Exception:
                pass
            reply = {"ok": False, "error": str(exc)}
        try:
            writer.write((json.dumps(reply, allow_nan=False) + "\n").encode())
            await asyncio.wait_for(writer.drain(), 0.25)
        finally:
            writer.close()
            await writer.wait_closed()

    async def watchdog():
        while True:
            try:
                controller.expire()
                if controller.active:
                    s = controller.poll()
                    if s.estop or not s.enabled or s.motion_mode != controller.api.TRAJ_MODE_TELEOP:
                        controller.stop()
            except Exception:
                # A broken LinuxCNC link must never keep renewing a lease.
                try:
                    controller.stop()
                except Exception:
                    pass
            await asyncio.sleep(0.02)

    server = await asyncio.start_unix_server(client, str(path), limit=2*1024*1024)
    path.chmod(0o600)
    task = asyncio.create_task(watchdog())
    try:
        async with server:
            await server.serve_forever()
    finally:
        task.cancel()
        try:
            controller.stop()
        finally:
            path.unlink(missing_ok=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/run/foamomatic/adapter.sock")
    parser.add_argument("--program-dir", default=str(Path.home() / "linuxcnc/nc_files"))
    parser.add_argument("--max-jog", type=float, default=5.0,
                        help="Maximum jog velocity in machine units/second")
    args = parser.parse_args()
    if not math.isfinite(args.max_jog) or args.max_jog <= 0:
        parser.error("--max-jog must be finite and positive")
    import linuxcnc
    asyncio.run(serve(Controller(linuxcnc, args.program_dir, args.max_jog), args.socket))

if __name__ == "__main__":
    main()
