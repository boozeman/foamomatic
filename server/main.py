"""Container gateway: bounded latest-state telemetry and session-bound commands."""
import asyncio
import json
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

SOCKET = os.getenv("FOAM_SOCKET", "/run/foamomatic/adapter.sock")
TOKEN = os.environ.get("FOAM_TOKEN", "")
ALLOWED = set(os.environ.get("FOAM_ORIGINS", "").split(","))
ALLOWED.discard("")
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
    yield

app = FastAPI(title="Foamomatic XYUV", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"service": "foamomatic", "status": "running"}

@app.websocket("/ws")
async def websocket(ws: WebSocket):
    if ws.headers.get("origin") not in ALLOWED:
        await ws.close(code=1008)
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
            await ws.close(code=1008)
            return
        if not secrets.compare_digest(auth["token"], TOKEN):
            await ws.close(code=1008)
            return
        await emit({"type": "ready", "axes": ["X", "Y", "U", "V"],
                    "jog_lease_ms": 400, "jog_renew_ms": 100})
        sender = asyncio.create_task(telemetry())
        async def receive():
            while True:
                msg = await ws.receive_json()
                if not isinstance(msg, dict) or msg.get("cmd") not in CONTROL_COMMANDS:
                    await emit({"type": "ack", "ok": False, "error": "Unsupported command"})
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
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, RuntimeError, OSError):
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
