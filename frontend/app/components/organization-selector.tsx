
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Building2, ChevronDown, Plus } from "lucide-react";

import type { Organization } from "@/lib/organizations";

type Props = {
  organizations: Organization[];
};

export default function OrganizationSelector({
  organizations,
}: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const requestedId = searchParams.get("organization");

  const selected =
    organizations.find((org) => org.id === requestedId) ??
    organizations[0];

  if (organizations.length === 0) {
    return (
      <Link
        href="/organizations/new"
        className="inline-flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-3 text-sm text-indigo-300 hover:bg-indigo-500/20"
      >
        <Plus size={16} />
        Create your first workspace
      </Link>
    );
  }

  return (
    <div className="relative inline-flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900 px-4 py-3">
      <Building2 size={18} className="text-indigo-400" />

      <label htmlFor="organization-selector" className="sr-only">
        Select organization
      </label>

      <select
        id="organization-selector"
        aria-label="Select organization"
        value={selected.id}
        onChange={(event) => {
          const params = new URLSearchParams(
            searchParams.toString(),
          );

          params.set("organization", event.target.value);

          router.push(`/?${params.toString()}`);
        }}
        className="max-w-56 appearance-none bg-transparent pr-7 text-sm font-medium text-white outline-none"
      >
        {organizations.map((organization) => (
          <option
            key={organization.id}
            value={organization.id}
            className="bg-slate-900 text-white"
          >
            {organization.name}
          </option>
        ))}
      </select>

      <ChevronDown
        size={16}
        className="pointer-events-none absolute right-3 text-slate-400"
      />
    </div>
  );
}
