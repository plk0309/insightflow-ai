
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const backendUrl = process.env.BACKEND_API_URL;

  if (!backendUrl) {
    return NextResponse.json(
      { detail: "Backend connection is not configured" },
      { status: 500 },
    );
  }

  // Read the HttpOnly cookie on the Next.js server.
  const token = request.cookies.get(
    "insightflow_session"
  )?.value;

  if (!token) {
    return NextResponse.json(
      { detail: "Authentication required" },
      { status: 401 },
    );
  }

  try {
    const response = await fetch(
      `${backendUrl}/api/v1/organizations`,
      {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      }
    );

    if (response.status === 401) {
      return NextResponse.json(
        { detail: "Session expired. Please sign in again." },
        { status: 401 },
      );
    }

    if (!response.ok) {
      return NextResponse.json(
        { detail: "Unable to load organizations" },
        { status: 502 },
      );
    }

    const organizations: unknown = await response.json();

    // Validate the upstream response before returning it.
    if (
      !Array.isArray(organizations) ||
      !organizations.every(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          typeof item.id === "string" &&
          typeof item.name === "string"
      )
    ) {
      return NextResponse.json(
        { detail: "Invalid organizations response" },
        { status: 502 },
      );
    }

    return NextResponse.json(organizations, {
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch {
    // Do not expose backend connection details or tokens.
    return NextResponse.json(
      { detail: "Organization service unavailable" },
      { status: 502 },
    );
  }
}

export async function POST(request: NextRequest) {
  const backendUrl = process.env.BACKEND_API_URL;
  const token = request.cookies.get("insightflow_session")?.value;

  if (!token) {
    return NextResponse.json(
      { detail: "Authentication required" },
      { status: 401 },
    );
  }

  if (!backendUrl) {
    return NextResponse.json(
      { detail: "Backend connection is not configured" },
      { status: 500 },
    );
  }

  // Restrict cookie-authenticated writes to the same origin.
  const origin = request.headers.get("origin");
  if (origin !== request.nextUrl.origin) {
    return NextResponse.json(
      { detail: "Invalid request origin" },
      { status: 403 },
    );
  }

  let payload: unknown;

  try {
    payload = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "Invalid JSON body" },
      { status: 400 },
    );
  }

  if (
    typeof payload !== "object" ||
    payload === null ||
    !("name" in payload) ||
    !("slug" in payload) ||
    typeof payload.name !== "string" ||
    typeof payload.slug !== "string"
  ) {
    return NextResponse.json(
      { detail: "Organization name and slug are required" },
      { status: 400 },
    );
  }

  const name = payload.name.trim();
  const slug = payload.slug.trim().toLowerCase();

  if (
  name.length < 2 ||
  name.length > 255 ||
  slug.length < 3 ||
  slug.length > 100 ||
  !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)
) {
    return NextResponse.json(
      { detail: "Invalid organization name or slug" },
      { status: 422 },
    );
  }

  try {
    const response = await fetch(
      `${backendUrl}/api/v1/organizations`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name, slug }),
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      },
    );

    if (response.status === 401) {
      return NextResponse.json(
        { detail: "Session expired. Please sign in again." },
        { status: 401 },
      );
    }

    if (response.status === 409) {
      return NextResponse.json(
        { detail: "Organization slug already exists" },
        { status: 409 },
      );
    }

    if (response.status === 422) {
      return NextResponse.json(
        { detail: "Invalid organization details" },
        { status: 422 },
      );
    }

    if (!response.ok) {
      return NextResponse.json(
        { detail: "Unable to create organization" },
        { status: 502 },
      );
    }

    const organization: unknown = await response.json();

    if (
      typeof organization !== "object" ||
      organization === null ||
      !("id" in organization) ||
      typeof organization.id !== "string" ||
      !("name" in organization) ||
      typeof organization.name !== "string"
    ) {
      return NextResponse.json(
        { detail: "Invalid organization response" },
        { status: 502 },
      );
    }

    return NextResponse.json(organization, {
      status: 201,
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Organization service unavailable" },
      { status: 502 },
    );
  }
}
