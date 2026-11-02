"""Bounded subprocess orchestration; the host event loop remains responsive."""
import asyncio
import json
import math
import sys

MAX_BYTES = 256 * 1024

def context_for(status, text):
    if not isinstance(text,str) or len(text.encode("utf-8")) > MAX_BYTES or not text.strip():
        raise ValueError("Preview requires 1..256 KiB of UTF-8 G-code")
    if status.linear_units not in (1, 1/25.4):
        # LinuxCNC installations may expose an approximately equal inch scale.
        if not math.isclose(status.linear_units, 1/25.4):
            raise ValueError("Unsupported machine units")
    index = status.g5x_index
    if index not in range(1,10):
        raise ValueError("Invalid active coordinate system")
    position = {a:status.actual_position[i] for a,i in (("X",0),("Y",1),("U",6),("V",7))}
    mm = 1 if status.linear_units == 1 else 25.4
    parameters = {"5220":str(index), "5210":"1"}
    for i in range(9):
        parameters[str(5221+20*(index-1)+i)] = str(status.g5x_offset[i])
        parameters[str(5211+i)] = str(status.g92_offset[i])
    parameters[str(5230+20*(index-1))] = str(status.rotation_xy)
    return {"text":text,"g5x_index":index,"parameters":parameters,
            "position":position,"position_mm":{a:v*mm for a,v in position.items()},
            "position_inches":[v*mm/25.4 for v in status.actual_position],
            "linear_units":status.linear_units}

async def generate(context):
    process = await asyncio.create_subprocess_exec(
        sys.executable,"-B","-m","adapter.preview_worker",
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    try:
        output,_ = await asyncio.wait_for(
            process.communicate(json.dumps(context,allow_nan=False).encode()),20)
        if process.returncode or len(output) > 8*1024*1024:
            raise ValueError("Preview interpreter failed or output too large")
        return json.loads(output)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
