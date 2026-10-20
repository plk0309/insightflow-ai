
import { NextRequest, NextResponse } from "next/server";

type RouteContext = {
  params: Promise<{
    organizationId: string;
  }>;
};

type DataSource = {
  id: string;
  organization_id: string;
  name: string;
  source_type: string;
  status: string;
  created_at: string;
  updated_at: string;
};

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isDataSource(value: unknown): value is DataSource {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const item = value as Record<string, unknown>;

  return (
    typeof item.id === "string" &&
    typeof item.organization_id === "string" &&
    typeof item.name === "string" &&
    typeof item.source_type === "string" &&
    typeof item.status === "string" &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string"
  );
}

export async function GET(
  request: NextRequest,
  context: RouteContext,
) {
  const { organizationId } = await context.params;

  // Check the organization identifier before constructing
  // the backend URL.
  if (!UUID_PATTERN.test(organizationId)) {
    return NextResponse.json(
      { detail: "Invalid organization identifier" },
      { status: 400 },
    );
  }

  // The JWT stays on the Next.js server.
  const token = request.cookies.get(
    "insightflow_session",
  )?.value;

  if (!token) {
    return NextResponse.json(
      { detail: "Authentication required" },
      { status: 401 },
    );
  }

  const backendUrl = process.env.BACKEND_API_URL;

  if (!backendUrl) {
    return NextResponse.json(
      { detail: "Backend connection is not configured" },
      { status: 500 },
    );
  }

  try {
    const backendResponse = await fetch(
      `${backendUrl}/api/v1/organizations/${organizationId}/data-sources`,
      {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      },
    );

    if (backendResponse.status === 401) {
      return NextResponse.json(
        {
          detail: "Session expired. Please sign in again.",
        },
        { status: 401 },
      );
    }

    if (backendResponse.status === 403) {
      return NextResponse.json(
        { detail: "Access denied" },
        { status: 403 },
      );
    }

    if (backendResponse.status === 404) {
      return NextResponse.json(
        { detail: "Organization not found" },
        { status: 404 },
      );
    }

    if (!backendResponse.ok) {
      return NextResponse.json(
        { detail: "Unable to load data sources" },
        { status: 502 },
      );
    }

    const data: unknown = await backendResponse.json();

    if (
      !Array.isArray(data) ||
      !data.every(isDataSource)
    ) {
      return NextResponse.json(
        { detail: "Invalid data source response" },
        { status: 502 },
      );
    }

    // Defense in depth: do not return records belonging
    // to a different organization.
    if (
      !data.every(
        (source) =>
          source.organization_id.toLowerCase() ===
          organizationId.toLowerCase(),
      )
    ) {
      return NextResponse.json(
        { detail: "Invalid organization data" },
        { status: 502 },
      );
    }

    return NextResponse.json(data, {
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch {
    // Never expose connection details or authentication data.
    return NextResponse.json(
      { detail: "Data source service unavailable" },
      { status: 502 },
    );
  }
}
