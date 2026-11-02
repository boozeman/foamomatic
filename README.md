# Foamomatic

XYUV-only LinuxCNC adapter and container gateway. Initial backend foundation;
includes a read-only browser status page; G-code upload/run, heater control and hardware watchdog integration are not implemented yet.
Not commissioned for operating a physical machine.

## Deployment architecture

Run LinuxCNC, its real-time Mesa driver and this small Python adapter on the
Debian host. Run the gateway in Docker on the same host. Dedicate one physical
Ethernet interface to Mesa, and another to operator LAN traffic. Do not bridge
Docker or route browser traffic through the Mesa interface.

The browser never streams step pulses or G-code line-by-line. In a future program
runner, upload the complete program before starting; LinuxCNC must execute it
locally. Gateway telemetry is 5 Hz, with no history queue. Rendering should use
the latest snapshot. Low bandwidth affects display freshness, not motion timing.
High latency deliberately prevents continuous remote jogging.

## Coordinates

Left endpoint is X horizontal, Y vertical. Right endpoint is U horizontal,
V vertical. LinuxCNC axis indices are 0,1,6,7; joint indices are separately
0,1,2,3, in that configured trivkins order. Configure exactly four XYUV joints.
Position/offset calculations use coordinate vectors, not joint vectors.

Wire visualization will use a straight segment between two tower planes;
tower distance and stock placement must be configured. A 3kg weight maintains
tension; no sag, stretch, or fixed-length constraint is modeled.

## Host installation

Use the Debian system Python that imports linuxcnc, not a new venv.
Run these commands on the Debian host from the foamomatic checkout, as the
same regular user who runs LinuxCNC.

1. With the machine idle, stop the manually started adapter with Ctrl+C.
2. Install and enable the service:

       sudo python3 deploy/install_systemd.py --user "$(id -un)"

The installer verifies LinuxCNC imports as that user, validates the generated
unit, installs it under /etc/systemd/system, and enables/restarts it.
The installed unit uses this checkout's absolute path and the operator's
numeric UID/GID. Keep the checkout in place; no /opt copy or venv is required.
The template deploy/foamomatic-adapter.service must be rendered by the installer,
not copied directly.

3. Set FOAM_UID and FOAM_GID in .env to the values printed by the installer.
4. Recreate the gateway to refresh its runtime-directory bind mount:

       docker compose up -d --force-recreate

Check service status and logs:

    systemctl status foamomatic-adapter --no-pager
    journalctl -u foamomatic-adapter -n 50 --no-pager

Service management:

    sudo systemctl restart foamomatic-adapter
    sudo systemctl stop foamomatic-adapter
    sudo systemctl disable --now foamomatic-adapter

Only stop/restart the adapter while the machine is idle. It does not resume
motion commands after restart. After adapter code updates, restart the service;
the installer need only be rerun when its unit, checkout path or user changes.

The service starts on boot and retries failures every five seconds, including
a failed LinuxCNC connection during startup. LinuxCNC itself must still be
started separately with the validated XYUV INI/HAL configuration. Do not launch
a second manual adapter while the service is active.

RuntimeDirectoryPreserve=yes retains /run/foamomatic across service stops so
Docker keeps seeing the same directory. The socket is recreated inside it.
The /run directory is recreated at host reboot: start the adapter before the
gateway. If the gateway was started first, recreate it after the adapter starts.
No systemd sandbox option that hides LinuxCNC's shared memory or temporary
files is enabled. /health checks only the gateway, not LinuxCNC readiness.

## Container

Copy .env.example to .env. Set a strong random FOAM_TOKEN, matching UID/GID and
exact browser origin(s), comma separated. For LAN access set FOAM_BIND_IP to the
host's operator-LAN IP. Use TLS/WSS through a reverse proxy for untrusted networks.
Do not set the bind IP to the Mesa interface.

    docker compose up --build

No privileged container, host PID/IPC sharing or LinuxCNC libraries in the image.
The host Unix socket directory is the only machine connection.
The CPU limit is an initial resource bound, not a real-time guarantee.
Run LinuxCNC latency tests under expected container/network load before deployment;
avoid image builds during cutting.

GET /health checks the gateway process only, not LinuxCNC readiness.
Connect to /ws with an allowed Origin. Within three seconds send:

    {"token":"your-token"}

Wait for ready. Commands are JSON objects with cmd. Supported commands:
manual, reset_estop, enable, disable, home_all, world, jog, stop, abort,
estop, pause. Commands acknowledge submission, not completed motion.
Inspect subsequent status before the next state transition.
Home in MANUAL, wait for all homed, then request world before jogging.

Jog: send {"cmd":"jog","axis":"U","velocity":1}. Velocity is in machine
units/second (default adapter cap 5; change --max-jog if needed).
The server returns jog_challenge. Reply immediately with
{"challenge":"the-returned-value"}. This proof expires after 250ms and is one-use.
While a physical/dead-man UI input remains held, repeat jog every 100ms,
waiting for each challenge/ack cycle. Never acknowledge a challenge after release.
On release/focus loss send stop. One axis at a time is supported initially.
Ordinary status traffic never renews a movement lease.

The host stops all four coordinate axes when the 400ms jog lease expires,
checked every 20ms. These are software scheduling targets, not hard real-time
bounds. Network latency plus stopping distance must be considered when setting
the jog speed. Stale queued jog requests require a fresh round trip before motion.
There is no automatic reconnect/retry of motion commands.

Disconnect releases that session's jog. Abort/stop/estop are available to every
authenticated session; only one session can jog. Loss of browser connection
does not currently abort an automatic program; run/resume are not exposed yet.
That policy, heater behavior, and host-independent HAL watchdog remain explicit
commissioning work. Browser E-stop is not a replacement for physical E-stop.

## Verification

    python -m unittest discover -s tests -v

Unit tests use a fake LinuxCNC API to check sparse UV coordinate mapping,
offsets, lease expiry, competing sessions, wrong geometry and jog validation.
Real LinuxCNC, Docker build and Mesa operation need Debian-host verification.


## Browser status page

Rebuild the gateway image after pulling these changes:

    docker compose up -d --build

Open http://linuxcnc.local:8080 and enter the FOAM_TOKEN from your .env.
FOAM_ORIGINS must include exactly http://linuxcnc.local:8080.
The token is used in memory for this connection; it is not saved to browser
storage or embedded in the served files. Click Connect again after a disconnect.

The page requests a read-only WebSocket session, which the server prevents from
sending control commands. It shows machine/work coordinates, homing state,
ESTOP, enable, mode, program state and the latest LinuxCNC error.
Coordinates use the machine's configured units; the adapter does not yet expose
a unit label. Numbers below half a displayed decimal step render as zero.
No wire geometry or movement controls are included in this first screen.

Status older than three seconds, unavailable adapter data, or a closed connection
clears the live values. Browser reconnection is manual. /health remains a
gateway-only liveness check.

Additional HTTP/WebSocket tests (fake adapter only):

    python -m pip install -r requirements.txt httpx
    python -m unittest discover -s tests -v


## XYUV visualization

The browser draws two parallel endpoint planes and a straight wire between
(X,Y) and (U,V). The nominal display width is 1000 mm, horizontal range 0..710 mm,
and vertical range 0..260 mm. These are visual reference bounds, NOT LinuxCNC
travel limits or measured tower spacing. Positions are shown without clamping.
This initial visualization assumes machine coordinates are in mm.

Configure FOAM_VIEW_WIDTH_MM, FOAM_VIEW_HORIZONTAL_MAX_MM and
FOAM_VIEW_VERTICAL_MAX_MM in .env (defaults 1000, 710, 260). If you maintain a
separate Compose file, add these names to the gateway environment mapping.
No volume is needed: .env on the host supplies persistent configuration.
After changes rebuild/recreate the gateway.

Drag the canvas to rotate. Clear Trail resets the local observation history;
Reset View restores the viewing angle. At most 2000 moving sample segments
are retained in browser memory. The current wire disappears on stale data.
A connection gap, >1.5 second sampling gap, homing-state or program-file change
breaks the trail. Page reload discards it. All observed movement is included:
heater state is not available. At 5 Hz, lines between samples are approximate;
this is not a G-code preview or proof of the physical cut surface.

Geometry checks: node tests/test_wire_geometry.mjs


## G-code preview

Upload a UTF-8 .ngc/.nc file using the browser's preview form after connecting.
The authenticated POST /preview sends at most 256 KiB to the host adapter.
The adapter invokes LinuxCNC's gcode.parse in a separate, time-limited process;
it never calls linuxcnc.command, opens a run program, or changes machine files.
Temporary uploaded files and a private parameter-file copy are deleted afterwards.
No persistent volume is needed for preview uploads.

G0/G1 paths use all four XYUV coordinates. G0 is dashed orange; G1 endpoints and
their swept surface are blue/purple. A slider selects the preview wire's position
and source line, independently of the live wire. Preview is limited to 12000
segments and 20 seconds of interpretation. Errors discard the entire preview.

LinuxCNC must be running and idle. The starting point, active WCS/G92 offsets
and XY rotation are captured at upload time. Output is in machine coordinates,
converted to mm. Re-upload after changing offsets or the intended starting
position. Inactive WCS parameters come from the disk parameter file and may
be stale. The standard interpreter is used, without machine-specific remaps,
INI startup code or external subroutine paths. G2/G3, probing, rigid tapping and
nonzero tool offsets are explicitly unsupported. Heater M codes are not executed
or simulated. This preview does not validate machine travel limits.

After updating: restart the host adapter (machine idle) and rebuild the gateway:

    sudo systemctl restart foamomatic-adapter
    docker compose up -d --build --force-recreate

Refresh the browser. Try examples/xyuv-preview.ngc in the preview form.
Host dependencies gcode and rs274 are supplied by the LinuxCNC installation;
they are not installed into Docker. Host-side interpreter integration still
requires validation on the actual Debian installation.
