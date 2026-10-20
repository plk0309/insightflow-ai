
import "server-only";

import { cookies } from "next/headers";

export type DataSource = {
  id: string;
  organization_id: string;
  name: string;
  source_type: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export async function getDataSources(
  organizationId: string,
): Promise<DataSource[]> {
  const token = (await cookies()).get(
    "insightflow_session",
  )?.value;

  const backendUrl = process.env.BACKEND_API_URL;

  if (!token || !backendUrl) {
    return [];
  }

  try {
    const response = await fetch(
      `${backendUrl}/api/v1/organizations/${encodeURIComponent(organizationId)}/data-sources`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      },
    );

    if (!response.ok) {
      throw new Error("Unable to load data sources");
    }

    const data: unknown = await response.json();

    if (
      !Array.isArray(data) ||
      !data.every(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          typeof item.id === "string" &&
          item.organization_id === organizationId &&
          typeof item.name === "string" &&
          typeof item.status === "string",
      )
    ) {
      throw new Error("Invalid data source response");
    }

    return data as DataSource[];
  } catch {
    throw new Error("Unable to load organization data sources");
  }
}
