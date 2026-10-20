
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  // Basic same-origin check for cookie-based authentication.
  const origin = request.headers.get("origin");

  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json(
      { detail: "Invalid request origin" },
      { status: 403 },
    );
  }

  const response = NextResponse.json({
    message: "Signed out successfully",
  });

  // Remove the HttpOnly authentication cookie.
  response.cookies.set("insightflow_session", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });

  return response;
}
