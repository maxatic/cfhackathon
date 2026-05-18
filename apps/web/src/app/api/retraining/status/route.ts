import { requestRetrainingStatus } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    tenant_id?: string;
    job_id?: string;
    poll_count?: number;
  };

  if (!body.tenant_id || !body.job_id) {
    return NextResponse.json({ error: "tenant_id and job_id are required" }, { status: 400 });
  }

  try {
    const job = await requestRetrainingStatus({
      tenant_id: body.tenant_id,
      job_id: body.job_id,
      poll_count: Number(body.poll_count ?? 1),
    });
    return NextResponse.json(job);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Retraining status request failed",
      },
      { status: 502 },
    );
  }
}
