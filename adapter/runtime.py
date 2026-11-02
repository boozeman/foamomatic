"""Linux-only runtime identity guard; PID plus start time avoids PID reuse."""
from pathlib import Path

class RuntimeUnavailable(RuntimeError):
    pass

def process_identity(pid, proc_root=Path("/proc")):
    try:
        text=(Path(proc_root)/str(pid)/"stat").read_text()
        # comm is parenthesized and can contain spaces or parentheses.
        fields=text[text.rfind(")")+2:].split()
        if fields[0] in ("Z","X"):
            return None
        return (int(pid),int(fields[19]))  # /proc/PID/stat field 22: starttime
    except (OSError,ValueError,IndexError):
        return None

def discover_runtime(proc_root=Path("/proc")):
    root=Path(proc_root)
    found=[]
    try:
        entries=list(root.iterdir())
    except OSError as exc:
        raise RuntimeUnavailable("Cannot inspect LinuxCNC runtime processes") from exc
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if (entry/"comm").read_text().strip()!="linuxcncsvr":
                continue
        except OSError:
            continue
        identity=process_identity(int(entry.name),root)
        if identity:
            found.append(identity)
    if len(found)!=1:
        raise RuntimeUnavailable("Waiting for one running linuxcncsvr process (found %s)" % len(found))
    return found[0]

class RuntimeGuard:
    def __init__(self,identity,proc_root=Path("/proc")):
        self.identity=identity
        self.proc_root=Path(proc_root)

    @classmethod
    def connect(cls,proc_root=Path("/proc")):
        return cls(discover_runtime(proc_root),proc_root)

    def check(self):
        if process_identity(self.identity[0],self.proc_root)!=self.identity:
            raise RuntimeUnavailable("LinuxCNC runtime stopped or restarted; reconnecting")
