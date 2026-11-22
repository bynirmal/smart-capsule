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

`render.yaml` in the repository root defines everything, and it is the **free plan**: one click,
$0, no PC of yours involved. In Render:

1. **New → Blueprint**, pick this repository, apply.
2. Wait for the health check on `/healthz` to go green, then open the URL.

**Free-plan limits** (Render's rules, not the app's): the service spins down after 15 minutes
without traffic and takes about a minute to wake on the next request; the container filesystem is
ephemeral, so **capsules are lost on every redeploy, restart or spin-down** and no disk can be
attached. Export the capsules you care about as `.scapsule` files and re-import them afterwards.
The blueprint sets no password; add `SMART_CAPSULE_PASSWORD` in the dashboard to lock the URL.

**Permanent library:** deploy `render.paid.yaml` instead — same image, `0.5c-512mb` instance
(~$7/mo) plus a 1 GB disk mounted at `/data`, so capsules survive deploys and restarts.

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
