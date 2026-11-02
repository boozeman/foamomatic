"""Install on Debian: sudo python3 deploy/install_systemd.py --user USERNAME."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

UNIT = "foamomatic-adapter.service"

def render(template, project_root, uid, gid):
    # WorkingDirectory is a single path value, not an ExecStart argument.
    # Surrounding quotes become literal path characters on supported Debian.
    path = str(project_root)
    if not path.startswith("/"):
        raise ValueError("Project path must be absolute")
    if any(c.isspace() or ord(c) < 32 or c in ('"', "'", "\\") for c in path):
        raise ValueError("Use a checkout path without whitespace, quotes or backslashes")
    path = path.replace("%", "%%")
    return (template.replace("@UID@", str(uid)).replace("@GID@", str(gid))
            .replace("@PROJECT_ROOT@", path))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True, help="Same account that runs LinuxCNC")
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("Run on the Debian host with sudo")
    import pwd
    operator = pwd.getpwnam(args.user)
    if operator.pw_uid == 0:
        parser.error("Use a non-root LinuxCNC operator account")
    root = Path(__file__).resolve().parent.parent
    if not (root / "adapter" / "main.py").is_file():
        parser.error("Missing adapter sources")
    # Check the exact interpreter and operator before changing system files.
    subprocess.run(["runuser", "-u", args.user, "--", "/usr/bin/python3", "-B", "-c",
                    "import linuxcnc, adapter.main"], cwd=root, check=True)
    content = render((root / "deploy" / UNIT).read_text(), root,
                     operator.pw_uid, operator.pw_gid)
    with tempfile.TemporaryDirectory(prefix="foamomatic-systemd-") as temp:
        candidate = Path(temp) / UNIT
        candidate.write_text(content)
        subprocess.run(["systemd-analyze", "verify", str(candidate)], check=True)
        subprocess.run(["install", "-m", "0644", str(candidate),
                        "/etc/systemd/system/" + UNIT], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", UNIT], check=True)
    subprocess.run(["systemctl", "restart", UNIT], check=True)
    print("Installed for UID=%s GID=%s from %s" %
          (operator.pw_uid, operator.pw_gid, root))
    print("Set FOAM_UID=%s and FOAM_GID=%s in .env." %
          (operator.pw_uid, operator.pw_gid))
    print("Check: systemctl status " + UNIT)
    print("Logs: journalctl -u " + UNIT + " -n 50 --no-pager")
    print("Recreate the gateway after installation: docker compose up -d --force-recreate")
    print("Keep this checkout in place; the service loads its code from it.")

if __name__ == "__main__":
    main()
