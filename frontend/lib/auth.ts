
import "server-only";

import { cookies } from "next/headers";

export type CurrentUser = {
  id: string;
  email: string;
  full_name: string | null;
};

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const cookieStore = await cookies();

  const token = cookieStore.get("insightflow_session")?.value;
  const backendUrl = process.env.BACKEND_API_URL;

  if (!token || !backendUrl) {
    return null;
  }

  try {
    const response = await fetch(`${backendUrl}/api/v1/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });

    if (!response.ok) {
      return null;
    }

    const user: unknown = await response.json();

    if (
      typeof user !== "object" ||
      user === null ||
      !("id" in user) ||
      !("email" in user) ||
      typeof user.id !== "string" ||
      typeof user.email !== "string"
    ) {
      return null;
    }

    return {
      id: user.id,
      email: user.email,
      full_name:
        "full_name" in user &&
        typeof user.full_name === "string"
          ? user.full_name
          : null,
    };
  } catch {
    return null;
  }
}
