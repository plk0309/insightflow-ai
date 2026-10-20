
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Database,
  LayoutDashboard,
  Plus,
  Settings,
  Sparkles,
  Table2,
  TerminalSquare,
} from "lucide-react";

import { getCurrentUser } from "@/lib/auth";
import { getOrganizations } from "@/lib/organizations";
import { getDataSources } from "@/lib/data-sources";

import LogoutButton from "@/app/components/logout-button";
import OrganizationSelector from "@/app/components/organization-selector";

// Sidebar navigation is currently a visual preview.
const navigation = [
  {
    label: "Overview",
    icon: LayoutDashboard,
    active: true,
  },
  {
    label: "Data Sources",
    icon: Database,
    active: false,
  },
  {
    label: "SQL Workspace",
    icon: TerminalSquare,
    active: false,
  },
  {
    label: "Reports",
    icon: BarChart3,
    active: false,
  },
  {
    label: "Settings",
    icon: Settings,
    active: false,
  },
];

type DashboardProps = {
  selectedOrganizationId?: string;
};

async function DashboardContent({
  selectedOrganizationId,
}: DashboardProps) {
  // Validate the HttpOnly session through FastAPI.
  const user = await getCurrentUser();

  // Redirect visitors without a valid session.
  if (!user) {
    redirect("/login");
  }

  // Get organizations accessible to the signed-in user.
  const organizations = await getOrganizations();

  // Match the organization selected in the URL.
  // Only organizations returned by FastAPI are eligible.
  const selectedOrganization =
    organizations.find(
      (organization) =>
        organization.id === selectedOrganizationId,
    ) ?? organizations[0];

  // Retrieve data sources for the selected organization.
  const dataSources = selectedOrganization
    ? await getDataSources(selectedOrganization.id)
    : [];

  const displayName = user.full_name?.trim() || user.email;
  const userInitial = displayName.charAt(0).toUpperCase();

  // Data-source count is real; the other two metrics
  // remain placeholders until those features are connected.
  const metrics = [
    {
      label: "Data Sources",
      value: String(dataSources.length),
      description:
        dataSources.length === 0
          ? "Connect your first database"
          : "Registered data sources",
      icon: Database,
    },
    {
      label: "Discovered Tables",
      value: "0",
      description: "No schemas discovered yet",
      icon: Table2,
    },
    {
      label: "Saved Reports",
      value: "0",
      description: "Your reports will appear here",
      icon: BarChart3,
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="flex min-h-screen">
        {/* SIDEBAR */}
        <aside className="hidden w-64 shrink-0 border-r border-white/10 bg-slate-900/60 p-6 md:flex md:flex-col">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600">
              <Sparkles size={21} />
            </div>

            <div>
              <h1 className="text-lg font-bold">
                InsightFlow AI
              </h1>

              <p className="text-xs text-slate-400">
                Intelligence workspace
              </p>
            </div>
          </div>

          {/* Navigation */}
          <nav className="mt-12 space-y-2">
            {navigation.map((item) => {
              const Icon = item.icon;

              return (
                <div
                  key={item.label}
                  className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm ${
                    item.active
                      ? "bg-indigo-600/20 font-medium text-indigo-300"
                      : "text-slate-400"
                  }`}
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                </div>
              );
            })}
          </nav>

          {/* LOGOUT */}
          <div className="mt-6 border-t border-white/10 pt-4">
            <LogoutButton />
          </div>

          {/* AI FEATURES */}
          <div className="mt-auto rounded-2xl border border-indigo-500/20 bg-indigo-500/10 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-indigo-300">
              <Sparkles size={16} />
              AI Analytics
            </div>

            <p className="mt-2 text-xs leading-5 text-slate-400">
              Ask questions about your data using natural language.
            </p>

            <p className="mt-3 text-xs font-medium text-indigo-300">
              Coming soon
            </p>
          </div>
        </aside>

        {/* MAIN CONTENT */}
        <main className="min-w-0 flex-1">
          {/* HEADER */}
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 px-6 py-5 lg:px-10">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.2em] text-indigo-400">
                Workspace
              </p>

              <div className="mt-2 flex flex-wrap items-center gap-4">
                <h2 className="text-xl font-semibold">
                  Overview
                </h2>

                <OrganizationSelector
                  organizations={organizations}
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="hidden items-center rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-400 sm:inline-flex">
                <Activity
                  size={13}
                  className="mr-2"
                />
                Frontend ready
              </span>

              <div
                className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold"
                title={user.email}
              >
                {userInitial}
              </div>
            </div>
          </header>

          {/* DASHBOARD BODY */}
          <div className="mx-auto max-w-7xl space-y-8 p-6 lg:p-10">
            {/* WELCOME SECTION */}
            <section className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-3xl font-bold tracking-tight">
                  Welcome, {displayName}
                </h3>

                <p className="mt-2 text-slate-400">
                  Turn connected data into actionable insights.
                </p>
              </div>

              <Link
                href="/organizations/new"
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500"
              >
                <Plus size={18} />
                Create Organization
              </Link>
            </section>

            {/* METRIC CARDS */}
            <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {metrics.map((metric) => {
                const Icon = metric.icon;

                return (
                  <div
                    key={metric.label}
                    className="rounded-2xl border border-white/10 bg-slate-900 p-6"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-slate-400">
                        {metric.label}
                      </p>

                      <Icon
                        size={20}
                        className="text-indigo-400"
                      />
                    </div>

                    <p className="mt-5 text-4xl font-bold">
                      {metric.value}
                    </p>

                    <p className="mt-2 text-xs text-slate-500">
                      {metric.description}
                    </p>
                  </div>
                );
              })}
            </section>

            {/* QUERY WORKSPACE AND AI */}
            <section className="grid gap-6 xl:grid-cols-3">
              {/* SQL WORKSPACE */}
              <div className="rounded-2xl border border-white/10 bg-slate-900 p-6 xl:col-span-2">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-lg font-semibold">
                      SQL Workspace
                    </h4>

                    <p className="mt-1 text-sm text-slate-400">
                      Explore your data with secure SQL queries.
                    </p>
                  </div>

                  <TerminalSquare className="text-indigo-400" />
                </div>

                <div className="mt-6 overflow-x-auto rounded-xl border border-white/10 bg-slate-950 p-5 font-mono text-sm leading-7">
                  <p className="text-indigo-300">
                    SELECT
                  </p>

                  <p className="pl-5 text-slate-200">
                    region,
                  </p>

                  <p className="pl-5 text-slate-200">
                    SUM(revenue) AS total_revenue
                  </p>

                  <p className="text-indigo-300">
                    FROM{" "}
                    <span className="text-slate-200">
                      sales
                    </span>
                  </p>

                  <p className="text-indigo-300">
                    GROUP BY{" "}
                    <span className="text-slate-200">
                      region;
                    </span>
                  </p>
                </div>

                <p className="mt-4 text-xs text-slate-500">
                  Preview only. Query execution will be enabled
                  after authentication and data-source integration.
                </p>
              </div>

              {/* AI INSIGHTS */}
              <div className="rounded-2xl border border-white/10 bg-slate-900 p-6">
                <div className="flex items-center gap-2">
                  <Sparkles
                    className="text-indigo-400"
                    size={20}
                  />

                  <h4 className="text-lg font-semibold">
                    AI Insights
                  </h4>
                </div>

                <p className="mt-3 text-sm leading-6 text-slate-400">
                  Soon you&apos;ll be able to ask questions such
                  as &ldquo;Which region generated the most
                  revenue?&rdquo;
                </p>

                <div className="mt-6 flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-400">
                  Explore upcoming features
                  <ArrowUpRight size={16} />
                </div>
              </div>
            </section>

            {/* FOOTER */}
            <p className="text-center text-xs text-slate-600">
              InsightFlow AI · Frontend v0.1
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}

// Next.js 16 with Cache Components:
// Keep request-dependent work inside Suspense.
type HomeProps = {
  searchParams: Promise<{
    organization?: string | string[];
  }>;
};

export default function Home({
  searchParams,
}: HomeProps) {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
          Loading your InsightFlow workspace...
        </div>
      }
    >
      <DashboardWithSelection searchParams={searchParams} />
    </Suspense>
  );
}

async function DashboardWithSelection({
  searchParams,
}: HomeProps) {
  const params = await searchParams;

  const selectedOrganizationId =
    typeof params.organization === "string"
      ? params.organization
      : undefined;

  return (
    <DashboardContent
      selectedOrganizationId={selectedOrganizationId}
    />
  );
}
