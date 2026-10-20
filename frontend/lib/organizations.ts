
import "server-only";

import { cookies } from "next/headers";

export type Organization = {
  id: string;
  name: string;
  slug: string;
  created_at: string;
};

export async function getOrganizations(): Promise<Organization[]> {
  const token = (await cookies()).get("insightflow_session")?.value;
  const backendUrl = process.env.BACKEND_API_URL;

  if (!token || !backendUrl) {
    return [];
  }

  try {
    const response = await fetch(
      `${backendUrl}/api/v1/organizations`,
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
      return [];
    }

    const data: unknown = await response.json();

    if (
      !Array.isArray(data) ||
      !data.every(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          typeof item.id === "string" &&
          typeof item.name === "string" &&
          typeof item.slug === "string",
      )
    ) {
      return [];
    }

    return data as Organization[];
  } catch {
    return [];
  }
}
