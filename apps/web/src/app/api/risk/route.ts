import { requestRisk } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    tenant_id?: string;
    sku?: string;
    horizon_weeks?: number;
    limit?: number;
  };

  if (!body.tenant_id || !body.sku) {
    return NextResponse.json({ error: "tenant_id and sku are required" }, { status: 400 });
  }

  try {
    const risk = await requestRisk({
      tenant_id: body.tenant_id,
      sku: body.sku,
      horizon_weeks: Math.max(1, Math.min(Number(body.horizon_weeks ?? 12), 52)),
      limit: Math.max(1, Math.min(Number(body.limit ?? 5), 20)),
    });
    return NextResponse.json(risk);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Risk ranking request failed",
      },
      { status: 502 },
    );
  }
}
