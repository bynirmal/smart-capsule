# Packaging Smart Capsule

The desktop application is packaged with **PyInstaller** in one-folder mode.
One-folder keeps startup fast and leaves the web client's static files visible
and editable, which matters for local-only software.

## Build

```bash
.venv\Scripts\activate
python -m pip install pyinstaller
pyinstaller packaging/smart_capsule.spec --noconfirm
```

Output:

```
dist/SmartCapsule/SmartCapsule.exe
```

The spec bundles:

* `webapp/static` → the browser client (HTML/CSS/JS)
* `database/migrations` → SQL schema migrations applied on first run
* every GUI page module (lazy-loaded, so PyInstaller cannot discover them alone)

Neural dependencies are excluded on purpose: the app must stay runnable without
PyTorch. Users who want the neural backend install the AI requirements into the
interpreter they package with.

## Verify a build

1. Double-click `SmartCapsule.exe`; the dashboard must show real storage and
   hardware figures.
2. `SmartCapsule.exe --smoke` prints `SMOKE RESULT: OK - 13 pages built and routed`.
3. `SmartCapsule.exe --web` starts the browser interface on `127.0.0.1:8765`.

User data lives outside the bundle (`%APPDATA%\SmartCapsule`), so upgrades never
touch capsules, attachments or backups.

## Not included

* Cloud synchronisation. The web API already exposes import/export for any
  external sync tool, and the reference PostgreSQL adapter is intentionally
  omitted: `psycopg2` ships compiled extensions that this machine's security
  policy blocks, and an untested database adapter would violate the project rule
  that no feature ships unverified.
* Code signing / installers (MSI, DMG). Add your organisation's signing step to
  the produced folder if needed.
