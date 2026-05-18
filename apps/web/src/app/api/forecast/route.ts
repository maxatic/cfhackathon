import { requestForecast } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    tenant_id?: string;
    sku?: string;
    customer_segment?: string;
    horizon_weeks?: number;
  };

  if (!body.tenant_id || !body.sku) {
    return NextResponse.json({ error: "tenant_id and sku are required" }, { status: 400 });
  }

  try {
    const forecast = await requestForecast({
      tenant_id: body.tenant_id,
      sku: body.sku,
      customer_segment: body.customer_segment ?? "all",
      horizon_weeks: Math.max(1, Math.min(Number(body.horizon_weeks ?? 12), 52)),
    });
    return NextResponse.json(forecast);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Forecast request failed",
      },
      { status: 502 },
    );
  }
}
