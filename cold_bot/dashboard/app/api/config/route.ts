import { readFileSync, writeFileSync } from "fs";
import path from "path";
import yaml from "js-yaml";
import { NextRequest, NextResponse } from "next/server";

const COLD_BOT_ROOT = path.join(process.cwd(), "..");
const CONFIG_PATH = path.join(COLD_BOT_ROOT, "config.yaml");

export async function GET() {
  try {
    const raw = readFileSync(CONFIG_PATH, "utf-8");
    const config = yaml.load(raw) as Record<string, unknown>;
    return NextResponse.json(config);
  } catch (e) {
    const message = e instanceof Error ? e.message : "Failed to read config";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    let config: Record<string, unknown>;
    try {
      const raw = readFileSync(CONFIG_PATH, "utf-8");
      config = (yaml.load(raw) as Record<string, unknown>) || {};
    } catch {
      config = {};
    }
    if (Array.isArray(body.start_urls)) {
      config.start_urls = body.start_urls;
    }
    if (body.source_type != null) {
      config.source_type = body.source_type;
    }
    if (body.facebook != null && typeof body.facebook === "object") {
      config.facebook = { ...(config.facebook as object || {}), ...(body.facebook as object) };
    }
    const out = yaml.dump(config, { lineWidth: 120, noRefs: true });
    writeFileSync(CONFIG_PATH, out, "utf-8");
    return NextResponse.json({ ok: true, message: "Config updated" });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Failed to write config";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
