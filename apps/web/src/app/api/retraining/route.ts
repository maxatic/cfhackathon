import { triggerRetraining } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    tenant_id?: string;
    reason?: string;
  };

  if (!body.tenant_id) {
    return NextResponse.json({ error: "tenant_id is required" }, { status: 400 });
  }

  try {
    const job = await triggerRetraining({
      tenant_id: body.tenant_id,
      reason: body.reason ?? "dashboard retraining trigger",
    });
    return NextResponse.json(job);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Retraining request failed",
      },
      { status: 502 },
    );
  }
}
