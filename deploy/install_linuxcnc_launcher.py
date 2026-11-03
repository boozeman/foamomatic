"""Install as the LinuxCNC operator from a terminal in the server desktop."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

UNIT = 'foamomatic-linuxcnc.service'


def session_start():
    if not os.environ.get('DISPLAY'):
        raise SystemExit('No desktop DISPLAY; run from the operator desktop terminal')
    names = [name for name in ('DISPLAY', 'XAUTHORITY', 'WAYLAND_DISPLAY',
                              'DBUS_SESSION_BUS_ADDRESS', 'XDG_CURRENT_DESKTOP') if name in os.environ]
    # Remove a previous session's optional values before importing this session.
    subprocess.run(['systemctl', '--user', 'unset-environment', 'XAUTHORITY', 'WAYLAND_DISPLAY'], check=True)
    subprocess.run(['systemctl', '--user', 'import-environment', *names], check=True)
    subprocess.run(['systemctl', '--user', 'start', UNIT], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ini', type=Path)
    parser.add_argument('--mesa-ip')
    parser.add_argument('--session-start', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() == 0:
        parser.error('Run on Linux as the regular LinuxCNC operator, without sudo')
    if args.session_start:
        session_start()
        return
    if not args.ini or not args.mesa_ip:
        parser.error('--ini and --mesa-ip are required')
    if not os.environ.get('DISPLAY'):
        parser.error('Run from a terminal in the operator desktop session')
    try:
        address = str(ipaddress.IPv4Address(args.mesa_ip))
    except ValueError:
        parser.error('--mesa-ip must be the Mesa card IPv4 address')
    ini = args.ini.expanduser().resolve()
    if not ini.is_file():
        parser.error('INI file does not exist')
    root = Path(__file__).resolve().parent.parent
    # Shared path restrictions also keep systemd and desktop Exec parsing simple.
    if any(c.isspace() or c in '\"\'\\%$`' for c in str(root)):
        parser.error('Checkout path must not contain whitespace or shell/systemd special characters')
    programs = {name: shutil.which(name) for name in ('linuxcnc', 'ping')}
    if not all(programs.values()):
        parser.error('Install LinuxCNC and iputils-ping first')
    home = Path.home()
    config_dir = home / '.config/foamomatic'
    unit_dir = home / '.config/systemd/user'
    autostart = home / '.config/autostart'
    for directory in (config_dir, unit_dir, autostart):
        directory.mkdir(parents=True, exist_ok=True)
    config = {'ini': str(ini), 'mesa_ip': address, **programs}
    (config_dir / 'linuxcnc.json').write_text(json.dumps(config, indent=2) + '\n')
    unit = (root / 'deploy' / UNIT).read_text().replace('@PROJECT_ROOT@', str(root))
    (unit_dir / UNIT).write_text(unit)
    desktop = ('[Desktop Entry]\nType=Application\nName=Foamomatic LinuxCNC launcher\n'
               'Exec=/usr/bin/python3 -B ' + str(root / 'deploy/install_linuxcnc_launcher.py') +
               ' --session-start\nTerminal=false\n')
    (autostart / 'foamomatic-linuxcnc.desktop').write_text(desktop)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemd-analyze', '--user', 'verify', str(unit_dir / UNIT)], check=True)
    print('Installed. Config: ' + str(config_dir / 'linuxcnc.json'))
    print('Start now: python3 deploy/install_linuxcnc_launcher.py --session-start')
    print('Subsequent desktop logins start the service automatically.')
    print('Keep the checkout in place. No machine enable/home/run commands are issued.')


if __name__ == '__main__':
    main()
