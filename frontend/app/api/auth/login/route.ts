
import { NextRequest, NextResponse } from "next/server";

type LoginResponse = {
  access_token: string;
  token_type: string;
};

export async function POST(request: NextRequest) {
  const backendUrl = process.env.BACKEND_API_URL;

  if (!backendUrl) {
    return NextResponse.json(
      { detail: "Backend connection is not configured" },
      { status: 500 },
    );
  }

  let payload: unknown;

  try {
    payload = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "Invalid request body" },
      { status: 400 },
    );
  }

  if (
    typeof payload !== "object" ||
    payload === null ||
    !("email" in payload) ||
    !("password" in payload) ||
    typeof payload.email !== "string" ||
    typeof payload.password !== "string"
  ) {
    return NextResponse.json(
      { detail: "Email and password are required" },
      { status: 400 },
    );
  }

  try {
    const backendResponse = await fetch(
      `${backendUrl}/api/v1/auth/login`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: payload.email,
          password: payload.password,
        }),
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      },
    );

    if (!backendResponse.ok) {
      return NextResponse.json(
        {
          detail:
            backendResponse.status === 401
              ? "Invalid email or password"
              : "Unable to sign in",
        },
        {
          status:
            backendResponse.status === 401
              ? 401
              : 502,
        },
      );
    }

    const data =
      (await backendResponse.json()) as LoginResponse;

    if (
      typeof data.access_token !== "string" ||
      !data.access_token ||
      data.token_type !== "bearer"
    ) {
      return NextResponse.json(
        { detail: "Invalid authentication response" },
        { status: 502 },
      );
    }

    const response = NextResponse.json({
      message: "Signed in successfully",
    });

    response.cookies.set(
      "insightflow_session",
      data.access_token,
      {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
      },
    );

    return response;
  } catch {
    return NextResponse.json(
      { detail: "Authentication service unavailable" },
      { status: 502 },
    );
  }
}
