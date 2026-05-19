import { requestPersonalization } from "@/lib/mcp-client";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    client_id?: string;
    additional_tokens?: string[];
  };

  if (!body.client_id) {
    return NextResponse.json({ error: "client_id is required" }, { status: 400 });
  }

  try {
    const result = await requestPersonalization({
      client_id: body.client_id,
      additional_tokens: body.additional_tokens?.slice(0, 8) ?? [],
    });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Personalization request failed",
      },
      { status: 502 },
    );
  }
}
