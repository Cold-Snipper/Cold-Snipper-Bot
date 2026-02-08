# Localhost Java UI

This is a Java-based localhost UI for testing Cold Bot scan controls, output monitoring,
and a local leads database (CSV-backed).

## Build

```bash
cd java_ui
./build.sh
# or: javac -d out src/Main.java
```

## Run

```bash
cd java_ui
java -cp out Main
```

Then open **http://localhost:1111** (standard port for Cold Bot).

**Real scrapers (website + FB) and site forms** are run by the UI via `python3` and scripts in `../cold_bot/`. For those to work, `python3` must have Playwright and deps. From the repo root:

```bash
cd cold_bot && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m playwright install chromium
```

Then start the Java UI from a shell where `python3` is the venv (e.g. `source cold_bot/.venv/bin/activate` then `cd java_ui && java -cp out Main`), or set `PATH="cold_bot/.venv/bin:$PATH"` before running the UI.

Override port via env or arg:

```bash
PORT=9090 java -cp out Main
# or: java -cp out Main 9090
```

## Notes

- UI is served from `static/`.
- Local DB (CSV) is stored at `data/leads.csv` with exports/backups in `data/`.
- API endpoints:
  - `POST /api/action?name=start_scan`
  - `POST /api/action?name=test_single_page`
  - `POST /api/action?name=mark_contacted` (form body `ids=1,2,3`)
  - `POST /api/action?name=export_csv`
  - `POST /api/action?name=backup_db`
  - `POST /api/action?name=clear_database`
  - `POST /api/action?name=clear_logs`
  - `GET /api/status`
  - `GET /api/logs?since=0`
  - `GET /api/leads?limit=200&q=miami`
