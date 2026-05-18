import { requestAnonymization } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    tenant_id?: string;
    sku?: string;
    customer_segment?: string;
    sample_size?: number;
    raw_order_rows?: Array<Record<string, unknown>>;
  };

  if (!body.tenant_id || !body.sku) {
    return NextResponse.json({ error: "tenant_id and sku are required" }, { status: 400 });
  }

  try {
    const report = await requestAnonymization({
      tenant_id: body.tenant_id,
      sku: body.sku,
      customer_segment: body.customer_segment ?? "all",
      sample_size: Math.max(1, Math.min(Number(body.sample_size ?? 8), 25)),
      raw_order_rows: body.raw_order_rows,
    });
    return NextResponse.json(report);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Anonymization request failed",
      },
      { status: 502 },
    );
  }
}
