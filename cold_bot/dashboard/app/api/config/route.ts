import { readFileSync } from "fs";
import path from "path";
import yaml from "js-yaml";
import { NextResponse } from "next/server";

const COLD_BOT_ROOT = path.join(process.cwd(), "..");

export async function GET() {
  try {
    const configPath = path.join(COLD_BOT_ROOT, "config.yaml");
    const raw = readFileSync(configPath, "utf-8");
    const config = yaml.load(raw) as Record<string, unknown>;
    return NextResponse.json(config);
  } catch (e) {
    const message = e instanceof Error ? e.message : "Failed to read config";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
