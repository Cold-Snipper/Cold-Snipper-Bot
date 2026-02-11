#!/bin/bash
# Reset localhost data, build, and run the Java UI for testing.
# Usage: ./run-and-test-localhost.sh [port]
set -e
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"
# Use cold_bot venv so Java-spawned python3 has Playwright and deps
VENV_PY="$REPO_ROOT/cold_bot/.venv/bin"
[ -d "$VENV_PY" ] && export PATH="$VENV_PY:$PATH"

PORT="${1:-1111}"

echo "=== Resetting local data (leads + FB queue) ==="
mkdir -p java_ui/data
printf '%s\n' "id,url,title,description,price,location,bedrooms,size,listing_type,contact_email,contact_phone,scan_time,status" > java_ui/data/leads.csv
printf '%s\n' "id,url,status,saved_at" > java_ui/data/fb_queue.csv
echo "  java_ui/data/leads.csv and fb_queue.csv cleared."

echo "=== Build Java UI ==="
cd java_ui
javac -d out src/Main.java
echo "  Build OK."

echo "=== Start UI on http://localhost:$PORT ==="
echo "  Open in browser: http://localhost:$PORT"
echo "  To test scrapers, ensure python3 has Playwright:"
echo "    cd cold_bot && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m playwright install chromium"
echo "  Then run this script from a shell where python3 is that venv (or PATH=cold_bot/.venv/bin:\$PATH)."
echo ""
exec java -cp out Main "$PORT"
