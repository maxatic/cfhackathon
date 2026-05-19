import { requestClients } from "@/lib/mcp-client";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const clients = await requestClients();
    return NextResponse.json(clients);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Client list request failed",
      },
      { status: 502 },
    );
  }
}
