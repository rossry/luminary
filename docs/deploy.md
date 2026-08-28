# Deploying a Luminary test server

A shared server so anyone on the team can open a browser, pick a geometry,
and test patterns — without running anything locally. The server is pure
Python (numpy wheels, no system deps, no database); state is one directory
(`var/`).

## Security model — read this first

Pattern upload (`POST /api/patterns`) **executes arbitrary Python
in-process** — that is by design (spec §15.5.2, trusted-operator model).
For shared deployments, run with **`--disable-pattern-upload`** (the unit
below does): the endpoint 403s server-side, uploads can't execute code no
matter what sits in front, and patterns ship via `git pull` + restart
instead. `GET /api/health` reports `"pattern_upload": false` so you can
verify.

With upload disabled the remaining write surface is geometry JSON only
(Pydantic-validated data, no code paths). Access control is still worth
having — anyone who can reach the box can fill the state disk — so
prefer one of:

- **Tailscale / WireGuard (recommended):** bind to the tailnet address and
  share the tailnet with the team. Zero exposed ports, no auth to build.
- **Reverse proxy with auth:** Caddy/nginx in front with basic auth + TLS
  (Caddy example below). The WebSocket (`/api/play`) proxies transparently.

Only re-enable pattern upload (drop the flag) on a server locked to people
you would hand a shell.

## Path 1 — plain VPS (recommended for iteration speed)

Best when you control the box and want `git pull && systemctl restart
luminary` as the whole update cycle. Needs Python ≥ 3.11.

```bash
sudo useradd -r -m -d /opt/luminary luminary
sudo -u luminary git clone https://github.com/rossry/luminary /opt/luminary/app
cd /opt/luminary/app
sudo -u luminary python3 -m venv /opt/luminary/venv
sudo -u luminary /opt/luminary/venv/bin/pip install -r requirements.txt

# one-time: demo geometries so the UI isn't empty (idempotent)
sudo -u luminary /opt/luminary/venv/bin/luminary seed \
    --state-dir /opt/luminary/var
```

`/etc/systemd/system/luminary.service`:

```ini
[Unit]
Description=Luminary pattern server
After=network.target

[Service]
User=luminary
WorkingDirectory=/opt/luminary/app
ExecStart=/opt/luminary/venv/bin/luminary \
    --state-dir /opt/luminary/var serve --host 127.0.0.1 --port 8080 \
    --disable-pattern-upload
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now luminary
```

Caddy in front (TLS + basic auth), `/etc/caddy/Caddyfile`:

```caddyfile
luminary.example.com {
    # "basicauth" works on every Caddy v2 (2.8 renamed it basic_auth;
    # Ubuntu's apt package predates the rename and rejects the new name)
    basicauth {
        # caddy hash-password
        team $2a$14$REPLACE_WITH_HASH
    }
    reverse_proxy 127.0.0.1:8080
}
```

Update cycle: `cd /opt/luminary/app && sudo -u luminary git pull && sudo
systemctl restart luminary`. Pattern files alone don't even need the
restart — upload them through the UI/API and the registry hot-reloads.

## Path 2 — Docker (for container platforms / hosts you don't control)

What Docker buys here: a pinned Python on hosts with old system Pythons,
direct deploys to Fly.io / Cloud Run / Railway (they take a Dockerfile and
give you a URL), and a container boundary around in-process pattern
execution. What it costs: image rebuilds in the update cycle. If you're on
your own VPS, prefer Path 1.

```bash
docker build -t luminary .
docker run -d --name luminary -p 127.0.0.1:8080:8080 \
    -v luminary-var:/data/var luminary
```

The image seeds the demo geometries on start (idempotent) and serves on
`0.0.0.0:8080` **inside the container** — the `-p 127.0.0.1:...` binding
keeps it loopback-only on the host; put the proxy/tailnet in front exactly
as in Path 1. On Fly.io: `fly launch` accepts the Dockerfile as-is; add a
volume for `/data/var` and put the app behind Fly's built-in
authentication or a tailnet, not on a bare public URL.

## Stage (play queue + audio)

`serve` runs the stage at `/stage` by default (`--no-stage` to skip): the
play queue that decides what the sphere is playing, persisted in
`var/stage/queue.json`. Its ticker idles whenever no viewer is connected,
no audio is playing, and the queue is exhausted, so it costs nothing to
leave on. For synchronized audio, install a player on the box — stock
Ubuntu ships none:

```bash
sudo apt install mpv        # or vlc / ffmpeg; auto-detected in that order
```

and drop files into `var/audio/` (`scp`, or however you move media). With
no player installed the stage still runs; entries just play silent (the
startup log says so once; `serve --audio-player CMD` overrides detection).
The default stage geometry is the production `pentagon-4A-33` capture;
`--stage-lights <geometry id | file>` substitutes another. A restart resumes
the current queue entry from its beginning — there is no mid-file audio
seek.

## Smoke test (either path)

```bash
curl -s localhost:8080/api/health     # {"status":"ok",...}
curl -s localhost:8080/api/lights     # seeded: hex-demo + pentagon-4A-35
```

Open the page, pick `hex-demo`, pick a pattern, press Play; the header's
B/light·frame readout confirms the wire codec is doing its job.

## Operational notes

- **State** is only the checkout's `var/` — geometry documents,
  pattern uploads, stage state and audio (`var/stage/`, `var/audio/`),
  and the mapping YAMLs (`var/mapping/`, and the tutorial's
  `var/mapping-demo/`). The directory ships in the repo
  (`var/.gitkeep`); its contents are gitignored. Back it up or
  volume-mount it; everything else is stateless and rebuilt from the
  repo. The default is anchored to the checkout, so no flag is needed;
  a unit passing the old removed flag will refuse to start — drop it,
  and move anything that landed under its directory into `var/`. The
  only irreplaceable content is hand-saved geometries and, once
  mapping has run, the mapping YAMLs.
- **CPU:** render+encode measures ~0.8 ms/frame for 2,048 lights
  (implementation-notes §7); each connected viewer runs its own engine, so
  budget roughly one core per handful of simultaneous viewers at 30 fps.
- **Patterns** on a locked-down server come from the repo: `git pull` then
  restart the service picks up new/changed files in `patterns/`. (With
  upload enabled instead, uploads land in `var/patterns-uploads/` and
  hot-reload without a restart.)
- **`/demo/mapping`** is the hardware-free deployment-mapping tutorial,
  mounted by `serve` by default (`--no-mapping-demo` to skip). Its frame
  ticker idles whenever no one is connected, so it costs nothing to leave
  on; every viewer shares the one simulated session, whose mapping
  records persist exactly like production's — `var/mapping-demo/`, same
  store code — and survive restarts until someone presses the page's
  ↺ restart.
