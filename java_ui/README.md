# Localhost Java UI

This is a Java-based localhost UI for testing Cold Bot scan controls, output monitoring,
and a local leads database (CSV-backed).

## Run

```bash
cd "/Users/karlodefinis/COLD BOT/java_ui"
/opt/homebrew/opt/openjdk/bin/javac -d out src/Main.java
/opt/homebrew/opt/openjdk/bin/java -cp out Main
```

Then open **http://localhost:1111** (standard port for Cold Bot).

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
