import { Suspense } from "react";
import type { Business } from "@/lib/booking";
import Booking from "./Booking";

import { API_INTERNAL as API } from "@/lib/server-api";

// The business + services are fetched on the server so the first paint already contains real content
// (no client-side fetch waterfall); the client takes over for stylists, slots and holds.
async function Data({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const biz = await fetch(`${API}/public/${slug}`, { cache: "no-store" })
    .then((r) => (r.ok ? (r.json() as Promise<Business>) : null))
    .catch(() => null);
  return <Booking slug={slug} initialBiz={biz} />;
}

function Shell() {
  return (
    <main className="mx-auto min-h-screen max-w-md overflow-x-hidden bg-cream px-4 pb-10 pt-4">
      <div className="mb-5 h-[138px]" /><div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-[76px] animate-pulse rounded-2xl bg-stone-200" />)}</div>
    </main>
  );
}

export default function Page({ params }: { params: Promise<{ slug: string }> }) {
  return (
    <Suspense fallback={<Shell />}>
      <Data params={params} />
    </Suspense>
  );
}
