"""Desktop-session LinuxCNC launcher; no LinuxCNC command API is used."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import signal
import shutil
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


def read_mesa_error(halcmd, parameter=None):
    """Read local HAL only; unknown/missing/ambiguous data is never a fault."""
    pattern = parameter or 'hm2_*.io_error'
    try:
        result = subprocess.run([halcmd, '-s', 'show', 'param', pattern],
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    values = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[-1].startswith('hm2_') and fields[-1].endswith('.io_error'):
            if fields[-2].upper() not in ('TRUE', 'FALSE'):
                return None
            values.append(fields[-2].upper() == 'TRUE')
    # Multiple cards require an explicit selection, not a guessed association.
    return values[0] if len(values) == 1 else None


def close_owned_linuxcnc(child, axis_remote):
    """Ask AXIS to exit so the foreground LinuxCNC script can clean up HAL."""
    requested = False
    if axis_remote:
        try:
            requested = subprocess.run([axis_remote, '--quit'], stdin=subprocess.DEVNULL,
                                       capture_output=True, timeout=3).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not requested:
        child.terminate()
    try:
        child.wait(timeout=25)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('LinuxCNC did not exit; refusing to launch another instance') from exc


class MesaHealth:
    def __init__(self):
        self.failures = 0
        self.healthy_seen = False
        self.unknown_logged = False

    def sample(self, value):
        if value is False:
            self.healthy_seen = True
        self.failures = self.failures + 1 if value is True else 0
        return self.failures >= 3


def supervise(config):
    stop = threading.Event()
    child = None
    health = MesaHealth()
    recovering = False
    halcmd = config.get('halcmd') or shutil.which('halcmd')
    axis_remote = config.get('axis_remote') or shutil.which('axis-remote')
    if not halcmd:
        raise RuntimeError('halcmd not found; install the LinuxCNC host tools')
    def shutdown(signum, frame):
        stop.set()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, shutdown)
    gate = PowerGate()
    print('Waiting for Mesa at ' + config['mesa_ip'], flush=True)
    try:
        while not stop.is_set():
            if child is not None:
                code = child.poll()
                if code is None:
                    value = read_mesa_error(halcmd, config.get('mesa_error_param'))
                    if value is None and not health.unknown_logged:
                        print('Mesa HAL status not available or ambiguous; waiting. '
                              'Check hm2_*.io_error and select --mesa-error-param for multiple cards.', flush=True)
                        health.unknown_logged = True
                    if health.sample(value):
                        print('Persistent Mesa io_error; shutting down owned LinuxCNC before reconnecting', flush=True)
                        recovering = health.healthy_seen
                        close_owned_linuxcnc(child, axis_remote)
                        # Reap before probing the network or considering another launch.
                    else:
                        stop.wait(2)  # Local HAL reads only; no Mesa network probes.
                        continue
                print('LinuxCNC exited (%s); %s' % (child.returncode,
                      'waiting for Mesa to reconnect' if recovering else
                      'power-cycle controller or restart this service to retry'), flush=True)
                child = None
                gate = PowerGate()
                gate.armed = recovering
                recovering = False
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
                    health = MesaHealth()
                    child = subprocess.Popen([config['linuxcnc'], '-r', config['ini']],
                                             cwd=str(Path(config['ini']).parent),
                                             stdin=subprocess.DEVNULL)
            stop.wait(2)
    finally:
        if child is not None and child.poll() is None:
            close_owned_linuxcnc(child, axis_remote)


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
