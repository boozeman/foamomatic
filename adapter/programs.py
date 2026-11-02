"""Immutable previewed program copies and a session-bound AUTO start sequence."""
import hashlib
import math
from pathlib import Path
import time
import uuid

WCS={1:"G54",2:"G55",3:"G56",4:"G57",5:"G58",6:"G59",7:"G59.1",8:"G59.2",9:"G59.3"}

def execution_text(context):
    preamble="%s G90 G94 G17 G40 G49 %s" % (
        "G21" if context["linear_units"]==1 else "G20",WCS[context["g5x_index"]])
    lines=context["text"].splitlines()
    delimiters=[i for i,line in enumerate(lines) if line.strip()=="%"]
    if delimiters:
        first=next((i for i,line in enumerate(lines) if line.strip()),None)
        if delimiters[0]!=first or len(delimiters)!=2:
            raise ValueError("Expected matching leading/trailing percent delimiters")
        lines[delimiters[0]]="(percent start)"
        lines[delimiters[1]]="M2 (percent end)"
    return preamble+"\n"+"\n".join(lines)+"\nM2\n"

def signature(s):
    return {"position":list(s.actual_position), "g5x":list(s.g5x_offset),
            "g92":list(s.g92_offset),"tool":list(s.tool_offset),
            "rotation":s.rotation_xy,"wcs":s.g5x_index,"units":s.linear_units}

def matches(expected,s):
    actual=signature(s)
    if actual["wcs"]!=expected["wcs"] or actual["units"]!=expected["units"]:
        return False
    for key in ("position","g5x","g92","tool"):
        if len(actual[key])!=len(expected[key]) or not all(
            math.isclose(a,b,rel_tol=0,abs_tol=0.001 if key=="position" else 1e-6)
            for a,b in zip(actual[key],expected[key])):
            return False
    return math.isclose(actual["rotation"],expected["rotation"],rel_tol=0,abs_tol=1e-6)

class Programs:
    def __init__(self,directory):
        self.directory=Path(directory)/".foamomatic-programs"
        self.records={}
        self.ticket=None
        self.running=None

    def save(self,text,baseline,loaded_file):
        # Retain the loaded/running file, discard other obsolete preview copies.
        for key,record in list(self.records.items()):
            if str(record["path"])!=loaded_file and key!=self.running:
                record["path"].unlink(missing_ok=True)
                del self.records[key]
        if len(self.records)>=4:
            raise ValueError("Too many retained programs; restart the adapter while idle")
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.directory.chmod(0o700)
        identity=uuid.uuid4().hex
        path=self.directory/(identity+".ngc")
        with path.open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(text)
        path.chmod(0o600)
        self.records[identity]={"path":path,"digest":hashlib.sha256(text.encode()).hexdigest(),
                                "baseline":baseline,"consumed":False}
        return identity

    def loaded(self,status):
        for key,record in self.records.items():
            if str(record["path"])==status.file:
                return key
        return None

    def ready(self,c,s,allow_pause=False):
        if (s.estop or not s.enabled or len(s.homed)<4 or not all(s.homed[:4]) or
                c.active or c.mdi_pending_serial is not None or
                any(j.get("homing",False) for j in getattr(s,"joint",()))):
            raise ValueError("Machine must be enabled, homed and free of manual activity")
        if not allow_pause and (s.interp_state!=c.api.INTERP_IDLE or s.paused):
            raise ValueError("Machine must be idle")

    def execute(self,c,msg,s):
        cmd=msg["cmd"]
        identity=msg.get("program_id")
        owner=msg["session"]
        record=self.records.get(identity) if isinstance(identity,str) else None
        if record is None:
            raise ValueError("Preview program is no longer available; upload it again")
        self.ready(c,s,cmd in ("program_pause","program_resume"))
        if hashlib.sha256(record["path"].read_bytes()).hexdigest()!=record["digest"]:
            raise ValueError("Program changed after preview; upload it again")
        if cmd in ("program_pause","program_resume"):
            if self.running!=identity or self.loaded(s)!=identity or s.task_mode!=c.api.MODE_AUTO:
                raise ValueError("This program is not running in AUTO")
            if cmd=="program_resume":
                if not s.paused:
                    raise ValueError("Program is not paused")
                c.command.auto(c.api.AUTO_RESUME)
            else:
                if s.paused or s.interp_state==c.api.INTERP_IDLE:
                    raise ValueError("Program is not running")
                c.command.auto(c.api.AUTO_PAUSE)
            return {}
        if record["consumed"]:
            raise ValueError("This start request was already used; upload again for a new run")
        if not matches(record["baseline"],s):
            raise ValueError("Starting position or offsets changed; preview the program again")
        if cmd=="program_prepare":
            if self.ticket and self.ticket["deadline"]>time.monotonic() and self.ticket["owner"]!=owner:
                raise ValueError("Another client is preparing a program")
            # Standard preview cannot validate machine-specific remaps.
            ini=c.api.ini(s.ini_filename)
            if ini.findall("RS274NGC","REMAP"):
                raise ValueError("Machine remaps are not supported by program preview/run yet")
            self.ticket={"owner":owner,"id":identity,"phase":"mode",
                         "deadline":time.monotonic()+15}
            c.command.mode(c.api.MODE_AUTO)
        else:
            t=self.ticket
            if not t or t["owner"]!=owner or t["id"]!=identity or t["deadline"]<time.monotonic():
                raise ValueError("Program preparation expired or was cancelled")
            if s.task_mode!=c.api.MODE_AUTO or s.echo_serial_number<t["serial"]:
                raise ValueError("Wait for LinuxCNC to acknowledge preparation")
            if cmd=="program_open":
                if t["phase"]!="mode":
                    raise ValueError("Program open was already requested")
                c.command.program_open(str(record["path"]))
                t["phase"]="open"
            elif cmd=="program_run":
                if t["phase"]!="open" or self.loaded(s)!=identity:
                    raise ValueError("Previewed program is not loaded")
                # Consume before issuing AUTO_RUN: an uncertain response is never replayed.
                record["consumed"]=True
                self.running=identity
                self.ticket=None
                c.command.auto(c.api.AUTO_RUN,0)
                return {"submitted":True}
            else:
                raise ValueError("Unsupported program command")
        self.ticket["serial"]=c.command.serial
        return {"serial":c.command.serial,"program_id":identity}
