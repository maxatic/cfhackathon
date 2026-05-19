import { requestAuditEvents } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    client_id?: string;
    limit?: number;
  };

  try {
    const events = await requestAuditEvents({
      client_id: body.client_id,
      limit: Math.max(1, Math.min(Number(body.limit ?? 10), 50)),
    });
    return NextResponse.json(events);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Audit events request failed",
      },
      { status: 502 },
    );
  }
}
