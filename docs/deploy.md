# Deploying the web app

The web client is a standard-library Python HTTP server with SQLite storage, so it needs a host
that runs a long-lived Python process **and** gives it a persistent disk. Static-only hosts
(GitHub Pages, Netlify, Vercel static) and Workers-style runtimes cannot run it.

## 0. Before anything else: set a password

A hosted copy sits on a public URL. Without `SMART_CAPSULE_PASSWORD` the server is open to anyone
who finds the address — including reading and deleting capsules.

With the variable set, every route (API and static files) answers `401` and the browser shows a
native login prompt; the password is the only credential, so use a long one. `/healthz` stays
public so platform health checks keep working.

Other deployment variables:

| Variable | Purpose |
| --- | --- |
| `PORT` | Port to bind (platforms inject this) |
| `SMART_CAPSULE_HOST` | Bind address; `0.0.0.0` in a container |
| `SMART_CAPSULE_ALLOW_REMOTE` | `1` permits non-loopback binds (required in a container) |
| `SMART_CAPSULE_HOME` | Data directory; must point at the mounted disk (`/data`) |
| `SMART_CAPSULE_PASSWORD` | Shared password gate described above |

## 1. Docker (any host)

```bash
docker build -t smart-capsule .
docker run -d --name smart-capsule \
  -p 8765:8765 \
  -e SMART_CAPSULE_PASSWORD='choose-a-long-one' \
  -v smart-capsule-data:/data \
  smart-capsule
```

Verified locally with `docker run` → `http://127.0.0.1:8765/` prompts for the password, captures a
capsule, and keeps it after `docker restart smart-capsule`.

## 2. Render (Blueprint)

`render.yaml` in the repository root defines everything. In Render:

1. **New → Blueprint**, pick this repository, apply.
2. When prompted for `SMART_CAPSULE_PASSWORD`, enter a long password (Render keeps it secret).
3. Wait for the health check on `/healthz` to go green, then open the URL; the browser asks for
   any username plus that password.

**Plan:** SQLite needs a disk, and Render only attaches disks to paid instance types, so the
blueprint uses `starter` (~$7/mo) with a 1 GB disk at `/data`.

To try it on the free plan instead, remove the `disk:` block and the `SMART_CAPSULE_HOME` variable.
The app then writes inside the container: it works, but every deploy or restart starts with an
empty library, and free instances sleep when idle.

## 3. Railway / Fly.io

Railway: **New Project → Deploy from GitHub repo**, add the same variables, and attach a volume at
`/data`. Fly.io: `fly launch` (it detects the Dockerfile), then `fly volumes create capsule_data
--size 1` and mount it at `/data` in `fly.toml`.

## 4. After the first deploy

- Open the URL, sign in, create a capsule, reload the page and confirm it is still listed.
- Restart/redeploy the service and confirm the capsule is **still** there — that proves the disk is
  actually mounted rather than container-local.
- Set `SMART_CAPSULE_PASSWORD` before sharing the URL with anyone.
- The browser extension cannot reach a hosted copy: its bridge is loopback-only by design, so the
  extension is for the local app only.

## Local run (no deployment)

```bash
python -m webapp                 # http://127.0.0.1:8765, no password
PORT=9000 python -m webapp       # custom port via environment
```
