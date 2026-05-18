import { requestModelVersions } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    tenant_id?: string;
  };

  if (!body.tenant_id) {
    return NextResponse.json({ error: "tenant_id is required" }, { status: 400 });
  }

  try {
    const versions = await requestModelVersions({
      tenant_id: body.tenant_id,
    });
    return NextResponse.json(versions);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Model versions request failed",
      },
      { status: 502 },
    );
  }
}
