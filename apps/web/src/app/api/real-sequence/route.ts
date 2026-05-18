import { requestRealSequence } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    client_id?: string;
    start_sequence?: string;
    max_generate?: number;
    temperature?: number;
    top_k?: number;
    seed?: number;
  };

  try {
    const result = await requestRealSequence({
      client_id: body.client_id ?? "nexus_lab_solutions",
      start_sequence: body.start_sequence || undefined,
      max_generate: Math.max(1, Math.min(Number(body.max_generate ?? 30), 80)),
      temperature: Math.max(0.1, Math.min(Number(body.temperature ?? 1), 2)),
      top_k: Math.max(1, Math.min(Number(body.top_k ?? 30), 100)),
      seed: Number(body.seed ?? 0),
    });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Real sequence model request failed",
      },
      { status: 502 },
    );
  }
}
