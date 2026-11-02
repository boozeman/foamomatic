# Foamomatic

XYUV-only LinuxCNC adapter and container gateway. Initial backend foundation;
no frontend, G-code upload/run, heater control or hardware watchdog integration yet.
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

Use the system Python that imports linuxcnc, not a new venv. Copy this project
to /opt/foamomatic (or adjust the unit). Edit deploy/foamomatic-adapter.service:
User and Group MUST match the LinuxCNC operator, and FOAM_UID/GID must match
that account. Socket ownership is the local access boundary.

Install the unit as /etc/systemd/system/foamomatic-adapter.service, then run:

    sudo systemctl daemon-reload
    sudo systemctl start foamomatic-adapter

Start LinuxCNC separately with the machine's validated XYUV INI/HAL config.
The adapter stays available when LinuxCNC is not running, but status and control
return explicit errors. No real-machine INI or Mesa pin assignment is supplied.

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
