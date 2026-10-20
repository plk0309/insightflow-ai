
import { NextRequest, NextResponse } from "next/server";

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
    typeof payload.password !== "string" ||
    !("full_name" in payload) ||
    (payload.full_name !== null &&
      typeof payload.full_name !== "string")
  ) {
    return NextResponse.json(
      { detail: "Invalid registration details" },
      { status: 400 },
    );
  }

  if (
    payload.password.length < 12 ||
    payload.password.length > 128
  ) {
    return NextResponse.json(
      { detail: "Password must contain 12 to 128 characters" },
      { status: 400 },
    );
  }

  try {
    const backendResponse = await fetch(
      `${backendUrl}/api/v1/auth/register`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: payload.email,
          full_name: payload.full_name,
          password: payload.password,
        }),
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      },
    );

    if (backendResponse.status === 409) {
      return NextResponse.json(
        { detail: "Email already registered" },
        { status: 409 },
      );
    }

    if (backendResponse.status === 422) {
      return NextResponse.json(
        { detail: "Invalid registration details" },
        { status: 422 },
      );
    }

    if (!backendResponse.ok) {
      return NextResponse.json(
        { detail: "Registration service unavailable" },
        { status: 502 },
      );
    }

    return NextResponse.json(
      { message: "Account created successfully" },
      { status: 201 },
    );
  } catch {
    return NextResponse.json(
      { detail: "Registration service unavailable" },
      { status: 502 },
    );
  }
}
