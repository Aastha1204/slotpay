import Link from "next/link";
import { Suspense } from "react";
import type { Business, Service } from "@/lib/booking";
import { advancePaise, inr } from "@/lib/booking";
import { Avatar, CategoryTile, HeroArt, LogoMark, Pin, STYLISTS, StepCalendar, StepChat, StepPay } from "@/components/art";
import Hero3D from "@/components/Hero3D";
import { Marquee, Reveal, Tilt } from "@/components/motion";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
const SLUG = "glow-studio";

const CATS = [
  { key: "hair", label: "Hair", blurb: "Cuts, colour, keratin, bridal trials" },
  { key: "skin", label: "Skin", blurb: "Clean-ups and glow facials" },
  { key: "nails", label: "Nails", blurb: "Manicures, gel polish, nail art" },
  { key: "spa", label: "Spa", blurb: "Head, shoulder and full-body massage" },
] as const;

// Fallback so the front page still renders if the API is asleep.
const FALLBACK: Business = {
  id: "", slug: SLUG, name: "Glow Studio Salon & Spa", address: "Shop 4, Gokhale Road, Naupada, Thane West, Maharashtra 400602",
  phone: "+91 99999 00000", email: "hello@glowstudio.demo", maps_url: "https://maps.google.com/?q=Thane+West", hold_minutes: 10,
  cancellation_cutoff_hours: 4, policy_text: "", open_now: false, closes_at: null, services: [],
};

const btnPrimary = "shine inline-flex items-center justify-center rounded-2xl bg-brand-700 px-6 py-4 text-base font-semibold text-white shadow-[0_10px_22px_-8px_rgba(2,132,199,0.60)] transition hover:-translate-y-0.5 active:scale-[0.98] active:shadow-[0_10px_22px_-8px_rgba(2,132,199,0.60)]";
const btnGhost = "raise inline-flex items-center justify-center rounded-2xl border border-line bg-white px-6 py-4 text-base font-semibold text-brand-900";

async function Landing() {
  const biz: Business = await fetch(`${API}/public/${SLUG}`, { cache: "no-store" })
    .then((r) => (r.ok ? (r.json() as Promise<Business>) : FALLBACK)).catch(() => FALLBACK);
  const book = `/b/${biz.slug}`;
  const byCat = (k: string) => biz.services.filter((s) => s.category === k);
  const popular: Service[] = CATS.flatMap((c) => byCat(c.key).slice(0, 2)).slice(0, 6);
  const fromPrice = (k: string) => { const p = byCat(k).map((s) => s.price_paise); return p.length ? inr(Math.min(...p)) : null; };

  return (
    <div className="overflow-x-clip bg-cream text-brand-900">
      {/* NAV */}
      <header className="sticky top-0 z-30 border-b border-line bg-cream/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <Link href="/" className="flex items-center gap-2.5" aria-label={`${biz.name} home`}>
            <LogoMark className="h-10 w-10" />
            <span className="tracking-tight text-lg font-bold leading-tight">Glow Studio<span className="block font-sans text-[11px] font-medium text-stone-500">Salon &amp; Spa · Thane West</span></span>
          </Link>
          <nav className="ml-auto hidden items-center gap-6 text-sm font-semibold md:flex" aria-label="Main">
            <a href="#services" className="hover:text-brand-700">Services</a>
            <a href="#how" className="hover:text-brand-700">How it works</a>
            <a href="#team" className="hover:text-brand-700">Team</a>
            <a href="#visit" className="hover:text-brand-700">Visit</a>
            {process.env.NEXT_PUBLIC_PROTOTYPE === "1" && <Link href="/prototype" className="rounded-full bg-brand-50 px-3 py-1 text-brand-700 ring-1 ring-brand-200">Prototype hub</Link>}
          </nav>
          <a href={book} className="shine ml-auto rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white shadow-[0_10px_22px_-8px_rgba(2,132,199,0.60)] active:scale-[0.98] active:shadow-sm md:ml-0">Book now</a>
        </div>
      </header>

      {/* HERO */}
      <section className="bg-aurora relative">
        {/* drifting background shapes (pure CSS depth) */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
          <span className="animate-drift absolute -left-10 top-24 h-28 w-28 rounded-[2rem] bg-brand-100" />
          <span className="animate-drift absolute right-[8%] top-10 h-12 w-12 rounded-full bg-gold [animation-delay:-3s]" />
          <span className="animate-drift absolute bottom-10 left-[42%] h-16 w-16 rotate-12 rounded-2xl bg-blush [animation-delay:-5s]" />
          <span className="animate-drift absolute right-[-30px] bottom-24 h-24 w-24 rounded-full bg-sage [animation-delay:-1.5s]" />
        </div>
        <div className="relative mx-auto grid max-w-6xl items-center gap-6 px-4 pb-14 pt-10 md:grid-cols-2 md:pt-16">
          <div>
            <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-line bg-gold px-3 py-1 text-xs font-bold uppercase tracking-wide">
              <span className={`h-2 w-2 rounded-full ${biz.open_now ? "bg-emerald-600" : "bg-stone-500"}`} />{biz.open_now ? "Open now" : "Book for later today"}
            </p>
            <h1 className="tracking-tight text-4xl font-extrabold leading-[1.08] sm:text-5xl lg:text-6xl">
              Book your <span className="relative whitespace-nowrap text-brand-700">glow<svg className="absolute -bottom-2 left-0 w-full" viewBox="0 0 120 10" preserveAspectRatio="none" aria-hidden><path d="M2 6c20-6 36 4 56-1s40-4 60 0" stroke="#38bdf8" strokeWidth="5" fill="none" strokeLinecap="round" /></svg></span> in 60 seconds.
            </h1>
            <p className="mt-5 max-w-md text-lg text-stone-700">Pick a service and a stylist, choose a time, pay a small advance, and you&apos;re confirmed. No calls, no waiting.</p>
            <div className="mt-7 flex flex-wrap gap-3">
              <a href={book} className={btnPrimary}>Book an appointment</a>
              <a href="#services" className={btnGhost}>See services</a>
            </div>
            <ul className="mt-8 grid gap-2 text-sm font-semibold sm:grid-cols-3">
              {[["₹100–₹200", "advance only"], ["WhatsApp", "confirmation"], [`${biz.cancellation_cutoff_hours} h`, "free cancellation"]].map(([a, b]) => (
                <li key={a} className="raise rounded-2xl border border-line bg-white px-3 py-2"><span className="block tracking-tight text-lg text-brand-700">{a}</span><span className="text-stone-600">{b}</span></li>
              ))}
            </ul>
          </div>
          <Hero3D><HeroArt className="h-full w-full" /></Hero3D>
        </div>
      </section>

      {/* MARQUEE */}
      <div className="border-y border-line bg-brand-50 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-brand-700">
        <Marquee items={["Hair", "Skin", "Nails", "Spa", "Bridal", "Colour", "Keratin", "Facials", "Massage"]} />
      </div>

      {/* SERVICES */}
      <section id="services" className="scroll-mt-20 border-b border-line bg-white py-16">
        <div className="mx-auto max-w-6xl px-4">
          <Reveal><h2 className="tracking-tight text-3xl font-extrabold sm:text-4xl">What would you like today?</h2>
            <p className="mt-2 text-stone-600">Prices include GST. Pay only a small advance online; the rest at the salon.</p></Reveal>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {CATS.map((c, i) => (
              <Reveal key={c.key} delay={i * 90}>
                <Tilt className="h-full"><a href={book} className="block h-full rounded-3xl border border-line bg-cream p-5 shadow-[0_12px_32px_-16px_rgba(2,132,199,0.40)]">
                  <CategoryTile category={c.key} size={64} />
                  <h3 className="mt-4 tracking-tight text-xl font-bold">{c.label}</h3>
                  <p className="mt-1 text-sm text-stone-600">{c.blurb}</p>
                  <p className="mt-3 text-sm font-bold text-brand-700">{fromPrice(c.key) ? `From ${fromPrice(c.key)}` : "View prices"} →</p>
                </a></Tilt>
              </Reveal>
            ))}
          </div>
          {popular.length > 0 && (
            <>
              <Reveal><h3 className="mb-3 mt-12 tracking-tight text-xl font-bold">Popular right now</h3></Reveal>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {popular.map((s, i) => (
                  <Reveal key={s.id} delay={(i % 3) * 80}>
                    <a href={book} className="raise flex items-center gap-3 rounded-2xl border border-line bg-white p-3">
                      <CategoryTile category={s.category} size={52} />
                      <span className="min-w-0 flex-1"><span className="block truncate font-semibold">{s.name}</span><span className="text-sm text-stone-500">{s.duration_min} min · {inr(s.price_paise)}</span></span>
                      <span className="shrink-0 rounded-full bg-gold px-2.5 py-1 text-xs font-bold">{inr(advancePaise(s))} advance</span>
                    </a>
                  </Reveal>
                ))}
              </div>
            </>
          )}
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16">
        <Reveal><h2 className="tracking-tight text-3xl font-extrabold sm:text-4xl">Three taps to confirmed</h2></Reveal>
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {[
            { n: 1, Art: StepCalendar, bg: "bg-brand-100", t: "Pick a slot", d: "Choose your service, stylist and a time. Live availability, so what you see is really free." },
            { n: 2, Art: StepPay, bg: "bg-gold-soft", t: "Pay a small advance", d: "UPI, cards or netbanking via Razorpay. Your slot is held for 10 minutes while you pay." },
            { n: 3, Art: StepChat, bg: "bg-sage", t: "Get it on WhatsApp", d: "Instant confirmation and reminders, with one-tap Reschedule or Cancel." },
          ].map((s, i) => (
            <Reveal key={s.n} delay={i * 130}>
              <Tilt className="h-full"><div className={`relative h-full rounded-3xl border border-line p-6 shadow-[0_12px_32px_-16px_rgba(2,132,199,0.40)] ${s.bg}`}>
                <span className="absolute -top-5 left-5 flex h-10 w-10 items-center justify-center rounded-full border border-line bg-white tracking-tight text-lg font-bold shadow-[0_12px_32px_-16px_rgba(2,132,199,0.40)]">{s.n}</span>
                <s.Art className="animate-float h-16 w-16" />
                <h3 className="mt-3 tracking-tight text-xl font-bold">{s.t}</h3>
                <p className="mt-1 text-stone-700">{s.d}</p>
              </div></Tilt>
            </Reveal>
          ))}
        </div>
      </section>

      {/* TEAM */}
      <section id="team" className="scroll-mt-20 border-y border-line bg-brand-100 py-16">
        <div className="mx-auto max-w-6xl px-4">
          <Reveal><h2 className="tracking-tight text-3xl font-extrabold sm:text-4xl">Meet your stylists</h2></Reveal>
          <div className="mt-10 grid grid-cols-2 gap-4 lg:grid-cols-4">
            {STYLISTS.map((s, i) => (
              <Reveal key={s.name} delay={i * 90}>
                <Tilt className="h-full"><a href={book} className="block h-full rounded-3xl border border-line bg-white p-4 text-center shadow-[0_12px_32px_-16px_rgba(2,132,199,0.40)]">
                  <Avatar {...s.art} className="animate-float mx-auto h-24 w-24" style={{ animationDelay: `-${i * 0.9}s` }} />
                  <h3 className="mt-3 tracking-tight text-lg font-bold">{s.name}</h3>
                  <p className="text-sm font-semibold text-brand-700">{s.title}</p>
                  <p className="mt-1 text-sm text-stone-600">{s.line}</p>
                </a></Tilt>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* VISIT */}
      <section id="visit" className="mx-auto grid max-w-6xl scroll-mt-20 gap-6 px-4 py-16 md:grid-cols-2">
        <Reveal>
          <h2 className="tracking-tight text-3xl font-extrabold sm:text-4xl">Come say hi</h2>
          <div className="mt-5 flex gap-4"><Pin className="animate-float h-12 w-12 shrink-0" /><div><p className="font-semibold">{biz.name}</p><p className="text-stone-700">{biz.address}</p></div></div>
          <p className="mt-4 text-stone-700">Open daily, 10 AM to 9 PM. Walk-ins welcome, but booking guarantees your slot.</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <a href={`tel:${biz.phone.replace(/\s/g, "")}`} className={btnGhost}>Call us</a>
            <a href={biz.maps_url} target="_blank" rel="noreferrer" className={btnGhost}>Get directions</a>
          </div>
        </Reveal>
        <Reveal delay={120}>
          <Tilt className="h-full"><div className="flex h-full flex-col justify-center rounded-3xl border border-line bg-brand-700 p-8 text-white shadow-[0_12px_32px_-16px_rgba(2,132,199,0.40)]">
            <h3 className="tracking-tight text-2xl font-bold">Your slot is waiting.</h3>
            <p className="mt-2 text-stone-300">Takes under a minute. Free cancellation until {biz.cancellation_cutoff_hours} hours before your visit.</p>
            <a href={book} className="shine mt-6 inline-flex items-center justify-center rounded-2xl bg-gold px-6 py-4 text-base font-bold text-brand-900 shadow-[0_12px_32px_-16px_rgba(2,132,199,0.40)] transition active:scale-[0.98] active:shadow-[0_12px_32px_-16px_rgba(2,132,199,0.40)]">Book now</a>
          </div></Tilt>
        </Reveal>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-6 text-sm text-stone-600 sm:flex-row sm:items-center sm:justify-between">
          <span>© {biz.name}. Prices include GST.</span>
          <nav className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Policies">
            <a className="underline" href={`/b/${biz.slug}/terms`}>Terms</a>
            <a className="underline" href={`/b/${biz.slug}/privacy`}>Privacy</a>
            <a className="underline" href={`/b/${biz.slug}/refund`}>Refund &amp; Cancellation</a>
            <a className="underline" href={`/b/${biz.slug}/contact`}>Contact</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}

export default function Home() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-cream" />}>
      <Landing />
    </Suspense>
  );
}
