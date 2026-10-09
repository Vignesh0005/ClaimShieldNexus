import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";
import { CLERK_ENABLED } from "@/lib/auth-config";

const isPublic = createRouteMatcher(["/", "/login(.*)", "/demo", "/api/v1/overlay(.*)"]);

const withClerk = clerkMiddleware(async (auth, req) => {
  if (!isPublic(req)) await auth.protect();
});

export default function middleware(req: NextRequest, event: NextFetchEvent) {
  if (!CLERK_ENABLED) return NextResponse.next();
  return withClerk(req, event);
}

export const config = {
  matcher: ["/((?!_next|.*\\.(?:ico|png|svg|jpg|jpeg|css|js|map|woff2?)).*)"],
};
