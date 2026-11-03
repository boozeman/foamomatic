"""Desktop-session LinuxCNC launcher; no LinuxCNC command API is used."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import signal
import subprocess
import threading


class PowerGate:
    """Two successful probes arm one launch; three failures rearm after exit."""
    def __init__(self):
        self.armed = True
        self.up = self.down = 0

    def sample(self, online):
        self.up = self.up + 1 if online else 0
        self.down = 0 if online else self.down + 1
        if self.down >= 3:
            self.armed = True
        if self.armed and self.up >= 2:
            self.armed = False
            return True
        return False


def linuxcnc_busy(proc=Path('/proc'), lock=Path('/tmp/linuxcnc.lock')):
    # Never invoke the LinuxCNC script against an existing instance: its lock
    # handling can offer to shut down that instance, even a different INI.
    if lock.exists():
        return True
    for entry in proc.iterdir():
        if entry.name.isdigit():
            try:
                if (entry / 'comm').read_text().strip() in ('linuxcncsvr', 'milltask', 'axis'):
                    return True
            except OSError:
                pass
    return False


def probe(address, ping):
    return subprocess.run([ping, '-n', '-c', '1', '-W', '1', address],
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=3).returncode == 0


def supervise(config):
    stop = threading.Event()
    child = None
    def shutdown(signum, frame):
        stop.set()
        if child is not None and child.poll() is None:
            child.terminate()  # LinuxCNC launcher handles SIGTERM and HAL cleanup.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, shutdown)
    gate = PowerGate()
    print('Waiting for Mesa at ' + config['mesa_ip'], flush=True)
    try:
        while not stop.is_set():
            if child is not None:
                code = child.poll()
                if code is None:
                    stop.wait(2)  # No Mesa probes while LinuxCNC owns the card.
                    continue
                print('LinuxCNC exited (%s); power-cycle controller or restart this service to retry' % code,
                      flush=True)
                child = None
                gate = PowerGate()
                gate.armed = False
            if linuxcnc_busy():
                # Respect manually started instances without touching their channels.
                gate = PowerGate()
                stop.wait(2)
                continue
            try:
                online = probe(config['mesa_ip'], config['ping'])
            except subprocess.TimeoutExpired:
                online = False
            if gate.sample(online) and not stop.is_set():
                # Recheck immediately before launch; never remove a LinuxCNC lock.
                if not linuxcnc_busy():
                    print('Mesa reachable; starting LinuxCNC: ' + config['ini'], flush=True)
                    child = subprocess.Popen([config['linuxcnc'], '-r', config['ini']],
                                             cwd=str(Path(config['ini']).parent),
                                             stdin=subprocess.DEVNULL)
            stop.wait(2)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    ipaddress.IPv4Address(config['mesa_ip'])
    if not Path(config['ini']).is_file():
        parser.error('Configured INI does not exist')
    if not os.environ.get('DISPLAY'):
        parser.error('No desktop DISPLAY; start from the LinuxCNC operator desktop session')
    supervise(config)


if __name__ == '__main__':
    main()
