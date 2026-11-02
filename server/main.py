"""Container gateway: bounded latest-state telemetry and session-bound commands."""
import asyncio
import json
import logging
import math
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

SOCKET = os.getenv("FOAM_SOCKET", "/run/foamomatic/adapter.sock")
TOKEN = os.environ.get("FOAM_TOKEN", "")
ALLOWED = {origin.strip() for origin in os.environ.get("FOAM_ORIGINS", "").split(",")}
ALLOWED.discard("")
log = logging.getLogger("uvicorn.error")
SAFE_COMMANDS = {"stop", "abort", "estop", "release"}
CONTROL_COMMANDS = {"reset_estop", "disable", "enable", "home_all", "manual",
                    "jog", "world", "pause"} | SAFE_COMMANDS

async def rpc(message):
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=65536), 0.5)
    try:
        writer.write((json.dumps(message, allow_nan=False) + "\n").encode())
        await asyncio.wait_for(writer.drain(), 0.25)
        return json.loads(await asyncio.wait_for(reader.readline(), 0.5))
    finally:
        writer.close()
        await writer.wait_closed()

@asynccontextmanager
async def lifespan(app):
    if len(TOKEN) < 32 or not ALLOWED:
        raise RuntimeError("Set FOAM_TOKEN (32+ characters) and exact FOAM_ORIGINS")
    for key, default in (("FOAM_VIEW_WIDTH_MM", "1000"),
                         ("FOAM_VIEW_HORIZONTAL_MAX_MM", "710"),
                         ("FOAM_VIEW_VERTICAL_MAX_MM", "260")):
        value = float(os.getenv(key, default))
        if not math.isfinite(value) or not 0 < value <= 100000:
            raise RuntimeError("Invalid visualization setting: " + key)
    yield

app = FastAPI(title="Foamomatic XYUV", lifespan=lifespan)
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

@app.get("/")
async def status_page():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

@app.get("/health")
async def health():
    return {"service": "foamomatic", "status": "running"}

@app.websocket("/ws")
async def websocket(ws: WebSocket):
    if ws.headers.get("origin") not in ALLOWED:
        log.warning("WebSocket rejected: origin not allowed")
        await ws.close(code=1008, reason="Origin not allowed")
        return
    await ws.accept()
    session = uuid.uuid4().hex
    sender = None
    output_lock = asyncio.Lock()
    async def emit(value):
        async with output_lock:
            await asyncio.wait_for(ws.send_json(value), 0.5)
    async def telemetry():
        while True:
            try:
                response = await rpc({"cmd": "status", "session": session})
            except Exception:
                response = {"ok": False, "error": "Adapter unavailable"}
            # No historical queue: sample next only after current send completes.
            await emit({"type": "status", **response})
            await asyncio.sleep(0.2)
    try:
        auth = await asyncio.wait_for(ws.receive_json(), 3)
        if not isinstance(auth, dict) or not isinstance(auth.get("token"), str):
            await ws.close(code=1008, reason="Invalid authentication message")
            return
        if not secrets.compare_digest(auth["token"].encode("utf-8"), TOKEN.encode("utf-8")):
            log.warning("WebSocket rejected: invalid token")
            await ws.close(code=1008, reason="Invalid token")
            return
        read_only = auth.get("read_only") is True
        geometry = {
            "width_mm": float(os.getenv("FOAM_VIEW_WIDTH_MM", "1000")),
            "horizontal_max_mm": float(os.getenv("FOAM_VIEW_HORIZONTAL_MAX_MM", "710")),
            "vertical_max_mm": float(os.getenv("FOAM_VIEW_VERTICAL_MAX_MM", "260")),
        }
        await emit({"type": "ready", "geometry": geometry, "read_only": read_only, "axes": ["X", "Y", "U", "V"],
                    "jog_lease_ms": 400, "jog_renew_ms": 100})
        sender = asyncio.create_task(telemetry())
        async def receive():
            while True:
                msg = await ws.receive_json()
                if not isinstance(msg, dict) or msg.get("cmd") not in CONTROL_COMMANDS:
                    await emit({"type": "ack", "ok": False, "error": "Unsupported command"})
                    continue
                if read_only:
                    await emit({"type": "ack", "ok": False, "error": "Read-only session"})
                    continue
                # Reject queued/stale motion: a one-use challenge is issued by
                # this gateway with a 250ms expiry for every jog operation.
                if msg["cmd"] == "jog":
                    challenge = secrets.token_hex(16)
                    await emit({"type": "jog_challenge", "challenge": challenge})
                    try:
                        proof = await asyncio.wait_for(ws.receive_json(), 0.25)
                    except asyncio.TimeoutError:
                        await rpc({"cmd": "release", "session": session})
                        continue
                    if not isinstance(proof, dict) or proof.get("challenge") != challenge:
                        await rpc({"cmd": "release", "session": session})
                        continue
                payload = {k: msg[k] for k in ("cmd", "axis", "velocity") if k in msg}
                payload["session"] = session
                try:
                    response = await rpc(payload)
                except Exception:
                    response = {"ok": False, "error": "Adapter unavailable"}
                await emit({"type": "ack", "cmd": msg["cmd"], **response})
        receiver = asyncio.create_task(receive())
        try:
            done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
        finally:
            receiver.cancel()
    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        log.warning("WebSocket closed: authentication or send timeout")
        await ws.close(code=1011, reason="Connection timeout")
    except Exception as exc:
        # Do not log messages/payloads: they can contain authentication data.
        log.error("WebSocket closed: internal error (%s)", type(exc).__name__)
        try:
            await ws.close(code=1011, reason="Internal server error")
        except RuntimeError:
            pass
    finally:
        if sender:
            sender.cancel()
        try:
            await rpc({"cmd": "release", "session": session})
        except Exception:
            pass
        try:
            await ws.close()
        except RuntimeError:
            pass
