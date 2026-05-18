import { requestForecastPlan } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    client_id?: string;
    intent?: string;
  };

  if (!body.client_id || !body.intent) {
    return NextResponse.json({ error: "client_id and intent are required" }, { status: 400 });
  }

  try {
    const plan = await requestForecastPlan({
      client_id: body.client_id,
      intent: body.intent,
    });
    return NextResponse.json(plan);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Forecast plan request failed",
      },
      { status: 502 },
    );
  }
}
