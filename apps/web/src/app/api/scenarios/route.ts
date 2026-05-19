import { requestScenarios } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    client_id?: string;
    start_sequence?: string[];
    beam_width?: number;
    horizon?: number;
    temperature?: number;
  };

  if (!body.client_id) {
    return NextResponse.json({ error: "client_id is required" }, { status: 400 });
  }

  try {
    const scenarios = await requestScenarios({
      client_id: body.client_id,
      start_sequence: body.start_sequence,
      beam_width: Math.max(1, Math.min(Number(body.beam_width ?? 3), 8)),
      horizon: Math.max(1, Math.min(Number(body.horizon ?? 8), 32)),
      temperature: Math.max(0.1, Math.min(Number(body.temperature ?? 1), 2)),
    });
    return NextResponse.json(scenarios);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Scenario request failed",
      },
      { status: 502 },
    );
  }
}
