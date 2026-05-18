import { requestPrediction } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    client_id?: string;
    start_sequence?: string[];
    max_generate?: number;
    top_k?: number;
    temperature?: number;
    seed?: number;
  };

  if (!body.client_id) {
    return NextResponse.json({ error: "client_id is required" }, { status: 400 });
  }

  try {
    const prediction = await requestPrediction({
      client_id: body.client_id,
      start_sequence: body.start_sequence,
      max_generate: Math.max(1, Math.min(Number(body.max_generate ?? 8), 80)),
      top_k: Math.max(1, Math.min(Number(body.top_k ?? 5), 100)),
      temperature: Math.max(0.1, Math.min(Number(body.temperature ?? 1), 2)),
      seed: typeof body.seed === "number" ? body.seed : undefined,
    });
    return NextResponse.json(prediction);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Prediction request failed",
      },
      { status: 502 },
    );
  }
}
