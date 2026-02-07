import { readFileSync } from "fs";
import path from "path";
import Database from "better-sqlite3";
import { NextResponse } from "next/server";
import yaml from "js-yaml";

const COLD_BOT_ROOT = path.join(process.cwd(), "..");

function getDbPath(): string {
  try {
    const configPath = path.join(COLD_BOT_ROOT, "config.yaml");
    const raw = readFileSync(configPath, "utf-8");
    const config = yaml.load(raw) as { database?: string };
    return path.join(COLD_BOT_ROOT, config?.database ?? "leads.db");
  } catch {
    return path.join(COLD_BOT_ROOT, "leads.db");
  }
}

export async function GET() {
  try {
    const dbPath = getDbPath();
    const db = new Database(dbPath, { readonly: true });
    const rows = db
      .prepare(
        `SELECT id, listing_hash, contact_email, source_url, status, channel, timestamp
         FROM lead_logs ORDER BY timestamp DESC LIMIT 200`
      )
      .all();
    db.close();
    return NextResponse.json(
      (rows as Record<string, unknown>[]).map((r) => ({
        ...r,
        time: r.timestamp ? new Date((r.timestamp as number) * 1000).toISOString() : null,
      }))
    );
  } catch (e) {
    if ((e as NodeJS.ErrnoException)?.code === "ENOENT") {
      return NextResponse.json([]);
    }
    const message = e instanceof Error ? e.message : "Failed to read logs";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
