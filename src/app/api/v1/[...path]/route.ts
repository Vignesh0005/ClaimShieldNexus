import { NextRequest, NextResponse } from "next/server";
import { ApiError, handle } from "@/lib/mock/db";

export const dynamic = "force-dynamic";

// The overlay endpoint is called from the browser extension on other origins.
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type, x-tenant-id",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

async function run(req: NextRequest, { params }: { params: { path: string[] } }) {
  if (process.env.NEXT_PUBLIC_USE_MOCK !== "true") {
    return NextResponse.json({ error: "The mock API is switched off. Data comes from the backend. Set NEXT_PUBLIC_USE_MOCK=true to use the mock." }, { status: 404, headers: CORS });
  }
  const tenantId = req.headers.get("x-tenant-id") || "meridian";
  let body: unknown = undefined;
  if (req.method === "POST") {
    try {
      body = await req.json();
    } catch {
      body = {};
    }
  }
  try {
    const data = handle(req.method, params.path, tenantId, req.nextUrl.searchParams, body);
    return NextResponse.json(data, { headers: CORS });
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    const message = e instanceof Error ? e.message : "Unexpected error.";
    return NextResponse.json({ error: message }, { status, headers: CORS });
  }
}

export const GET = run;
export const POST = run;

export function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}
