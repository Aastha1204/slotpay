import { Suspense } from "react";
import { notFound } from "next/navigation";
import type { Business } from "@/lib/booking";
import { PAGES, PolicyPage, policy } from "@/lib/policies";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

async function Content({ params }: { params: Promise<{ slug: string; page: string }> }) {
  const { slug, page } = await params;
  if (!(PAGES as readonly string[]).includes(page)) notFound();
  const res = await fetch(`${API}/public/${slug}`, { cache: "no-store" }).catch(() => null);
  if (!res || res.status === 404) notFound();
  if (!res.ok) return <p className="p-6 text-red-700">This page is temporarily unavailable.</p>;
  const biz = (await res.json()) as Business;
  const { title, sections } = policy(page as PolicyPage, biz);
  return (
    <main className="mx-auto min-h-screen max-w-2xl bg-cream px-5 py-8 text-brand-900">
      <p className="mb-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">This is a template generated from the business settings. {biz.name} must review it before going live.</p>
      <h1 className="mb-1 tracking-tight text-3xl font-semibold">{title}</h1>
      <p className="mb-6 text-sm text-stone-500">{biz.name}</p>
      {sections.map((s) => (
        <section key={s.h} className="mb-5">
          <h2 className="mb-1 text-lg font-semibold">{s.h}</h2>
          {s.p.map((t, i) => <p key={i} className="text-stone-700">{t}</p>)}
        </section>
      ))}
      <nav className="mt-8 flex flex-wrap gap-x-4 gap-y-1 border-t pt-4 text-sm">
        <a className="underline" href={`/b/${slug}`}>Book an appointment</a>
        {PAGES.map((p) => <a key={p} className="capitalize underline" href={`/b/${slug}/${p}`}>{p === "refund" ? "Refund & Cancellation" : p}</a>)}
      </nav>
    </main>
  );
}

export default function Page({ params }: { params: Promise<{ slug: string; page: string }> }) {
  return (
    <Suspense fallback={<div className="p-6 text-stone-500">Loading…</div>}>
      <Content params={params} />
    </Suspense>
  );
}
