
"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Sparkles,
} from "lucide-react";

function generateSlug(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100)
    .replace(/-+$/g, "");
}

export default function CreateOrganizationPage() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function handleNameChange(value: string) {
    setName(value);

    if (!slugEdited) {
      setSlug(generateSlug(value));
    }
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setError("");

    const cleanName = name.trim();
    const cleanSlug = slug.trim().toLowerCase();

    if (cleanName.length < 2 || cleanName.length > 255) {
      setError("Organization name must contain 2 to 255 characters.");
      return;
    }

    if (
      cleanSlug.length < 3 ||
      cleanSlug.length > 100 ||
      !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(cleanSlug)
    ) {
      setError(
        "Slug must contain 3 to 100 lowercase letters, numbers, or hyphens.",
      );
      return;
    }

    setLoading(true);

    try {
      const response = await fetch("/api/organizations", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: cleanName,
          slug: cleanSlug,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Unable to create organization",
        );
      }

      router.replace("/");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-5 py-12 text-white">
      <div className="w-full max-w-lg">
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-600">
              <Sparkles size={22} />
            </div>

            <div>
              <h1 className="text-xl font-bold">
                InsightFlow AI
              </h1>
              <p className="text-xs text-slate-400">
                Intelligence workspace
              </p>
            </div>
          </div>

          <Link
            href="/"
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white"
          >
            <ArrowLeft size={16} />
            Dashboard
          </Link>
        </div>

        <div className="rounded-3xl border border-white/10 bg-slate-900 p-8 shadow-2xl">
          <div className="mb-8">
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/15 text-indigo-400">
              <Building2 size={24} />
            </div>

            <h2 className="text-2xl font-bold">
              Create your organization
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-400">
              Set up a workspace to manage data sources,
              analytics, and team access.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label
                htmlFor="organization-name"
                className="mb-2 block text-sm font-medium text-slate-300"
              >
                Organization name
              </label>

              <input
                id="organization-name"
                type="text"
                autoComplete="organization"
                required
                minLength={2}
                maxLength={255}
                value={name}
                onChange={(event) =>
                  handleNameChange(event.target.value)
                }
                placeholder="Acme Analytics"
                className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-sm outline-none transition focus:border-indigo-500"
              />
            </div>

            <div>
              <label
                htmlFor="organization-slug"
                className="mb-2 block text-sm font-medium text-slate-300"
              >
                Workspace slug
              </label>

              <input
                id="organization-slug"
                type="text"
                required
                minLength={3}
                maxLength={100}
                value={slug}
                onChange={(event) => {
                  setSlugEdited(true);
                  setSlug(event.target.value.toLowerCase());
                }}
                placeholder="acme-analytics"
                className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-sm outline-none transition focus:border-indigo-500"
              />

              <p className="mt-2 text-xs text-slate-500">
                Use 3–100 lowercase letters, numbers, or hyphens.
                The slug must be unique.
              </p>
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 font-semibold transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading
                ? "Creating organization..."
                : "Create organization"}

              {!loading && <ArrowRight size={18} />}
            </button>
          </form>
        </div>

        <p className="mt-7 text-center text-xs text-slate-500">
          Your organization will be linked to your account.
        </p>
      </div>
    </main>
  );
}
