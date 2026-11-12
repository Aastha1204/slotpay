"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  ApiError, Business, Day, Hold, Service, Slot, SlotGroups, Stylist, advancePaise, api, fmtDay, fmtTime, inr,
  mmss,
} from "@/lib/booking";
import { Avatar, CategoryTile, LogoMark, STYLISTS } from "@/components/art";
import MonthCalendar from "./MonthCalendar";

const CATS = [["hair", "Hair"], ["skin", "Skin"], ["nails", "Nails"], ["spa", "Spa"]] as const;
const EMPTY: SlotGroups = { morning: [], afternoon: [], evening: [] };
const flat = (g: SlotGroups) => [...g.morning, ...g.afternoon, ...g.evening];
const btn = "w-full rounded-2xl bg-brand-700 px-5 py-4 text-base font-semibold text-white shadow-[0_10px_22px_-8px_rgba(2,132,199,0.60)] transition active:scale-[0.98] active:shadow-[0_10px_22px_-8px_rgba(2,132,199,0.60)] disabled:opacity-50";

export default function Booking({ slug: slugProp, initialBiz }: { slug?: string; initialBiz?: Business | null } = {}) {
  const routeParams = useParams<{ slug: string }>();
  const slug = slugProp ?? routeParams.slug;
  const router = useRouter();
  const sp = useSearchParams();
  const [biz, setBiz] = useState<Business | null>(initialBiz ?? null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [cat, setCat] = useState<string>("hair");
  const [stylists, setStylists] = useState<Stylist[]>([]);
  const [days, setDays] = useState<Day[]>([]);
  const [slots, setSlots] = useState<SlotGroups>(EMPTY);
  const [goneSlots, setGone] = useState<Slot[]>([]);
  const gone = useMemo(() => new Set(goneSlots.map((s) => s.start)), [goneSlots]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [hold, setHold] = useState<Hold | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const serviceId = sp.get("service"), staffId = sp.get("staff"), date = sp.get("date"), time = sp.get("time");
  const service = biz?.services.find((s) => s.id === serviceId) ?? null;
  const step = !service ? "service" : !staffId ? "stylist" : !date || !time ? "time" : hold ? "held" : "details";

  const go = useCallback((patch: Record<string, string | null>) => {
    const q = new URLSearchParams(sp.toString());
    Object.entries(patch).forEach(([k, v]) => (v === null ? q.delete(k) : q.set(k, v)));
    router.push(`?${q.toString()}`);
  }, [sp, router]);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

  // business + resume hold
  useEffect(() => {
    if (!initialBiz) api<Business>(`/public/${slug}`).then(setBiz).catch(fail);
    try {
      const h = JSON.parse(sessionStorage.getItem(`hold:${slug}`) ?? "null") as Hold | null;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (h?.hold_expires_at && new Date(h.hold_expires_at).getTime() > Date.now()) setHold(h);
    } catch { /* storage unavailable */ }
  }, [slug, initialBiz]);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(null), 3500); return () => clearTimeout(t); } }, [toast]);

  // stylists for the chosen service
  const loadStylists = useCallback(() => {
    if (!serviceId) return;
    api<{ stylists: Stylist[] }>(`/public/${slug}/stylists?service_id=${serviceId}`).then((r) => { setStylists(r.stylists); setError(null); }).catch(fail);
  }, [slug, serviceId]);
  useEffect(() => { loadStylists(); }, [loadStylists]);

  const staffQ = staffId && staffId !== "any" ? `&staff_id=${staffId}` : "";
  const loadDays = useCallback(() => {
    if (!serviceId || !staffId) return;
    api<{ days: Day[] }>(`/public/${slug}/days?service_id=${serviceId}&days=31${staffQ}`).then((r) => setDays(r.days)).catch(fail);
  }, [slug, serviceId, staffId, staffQ]);
  useEffect(loadDays, [loadDays]);

  // slots for the chosen day: realtime + 10 s poll + refetch on focus
  const prev = useRef<Slot[]>([]);
  const loadSlots = useCallback((quiet = false) => {
    if (!serviceId || !staffId || !date) return;
    if (!quiet) setLoadingSlots(true);
    api<{ slots: SlotGroups }>(`/public/${slug}/slots?service_id=${serviceId}&date=${date}${staffQ}`)
      .then((r) => {
        const next = flat(r.slots), have = new Set(next.map((s) => s.start));
        const removed = prev.current.filter((s) => !have.has(s.start));
        if (quiet && removed.length) {
          const mine = time;
          const others = removed.filter((s) => s.start !== mine);
          if (others.length) {
            setGone(others);
            setToast(`${fmtTime(others[0].start)} was just booked`);
            setTimeout(() => setGone([]), 2500);
          }
        }
        prev.current = next;
        setSlots(r.slots);
        setError(null);
      })
      .catch(fail)
      .finally(() => setLoadingSlots(false));
  }, [slug, serviceId, staffId, date, staffQ, time]);
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { prev.current = []; loadSlots(); }, [serviceId, staffId, date]);
  useEffect(() => {
    if (step !== "time" && step !== "details") return;
    const poll = setInterval(() => { loadSlots(true); loadDays(); }, 10000);
    const onFocus = () => loadSlots(true);
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(poll); window.removeEventListener("focus", onFocus); };
  }, [step, loadSlots, loadDays]);
  useEffect(() => {
    if (!biz || !date || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) return;
    const ch = supabase.channel(`slots:${biz.id}:${date}`)
      .on("broadcast", { event: "slot_held" }, () => loadSlots(true))
      .on("broadcast", { event: "slot_released" }, () => loadSlots(true))
      .subscribe();
    return () => { supabase.removeChannel(ch); };
  }, [biz, date, loadSlots]);

  // hold countdown / expiry
  const left = hold?.hold_expires_at ? new Date(hold.hold_expires_at).getTime() - now : 0;
  const expired = !!hold && left <= 0;
  const clearHold = () => { setHold(null); try { sessionStorage.removeItem(`hold:${slug}`); } catch { /* */ } };

  async function release() {
    if (hold) await api(`/public/holds/${hold.booking_id}/release`, { method: "POST", body: JSON.stringify({ public_token: hold.public_token }) }).catch(() => {});
    clearHold();
  }

  if (error && !biz) return <Shell><Banner tone="error">{error}</Banner><button className={btn} onClick={() => location.reload()}>Try again</button></Shell>;
  if (!biz) return <Shell><div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-stone-200" />)}</div></Shell>;

  const back = () => {
    if (step === "held") return release();
    router.back();
  };

  return (
    <Shell wide={step === "time"}>
      <Header biz={biz} />
      {step !== "service" && (
        <button onClick={back} className="mb-3 py-2 text-sm font-medium text-brand-700">← Back</button>
      )}
      {notice && <Banner tone="warn">{notice}</Banner>}
      {error && <Banner tone="error">{error} <button className="underline" onClick={() => { setError(null); loadStylists(); loadSlots(); loadDays(); }}>Retry</button></Banner>}
      {toast && <div className="fixed inset-x-4 top-4 z-20 rounded-xl bg-brand-700 px-4 py-3 text-center text-sm text-white shadow-lg">{toast}</div>}

      {step === "service" && (
        <section className="animate-step">
          <h2 className="mb-3 text-lg font-semibold">Choose a service</h2>
          <div className="mb-4 flex gap-2 overflow-x-auto" role="tablist">
            {CATS.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={cat === k} onClick={() => setCat(k)}
                className={`flex shrink-0 items-center gap-2 rounded-full border border-line py-1.5 pl-1.5 pr-4 text-sm font-semibold ${cat === k ? "bg-brand-700 text-white" : "bg-white text-brand-900"}`}><CategoryTile category={k} size={28} />{label}</button>
            ))}
          </div>
          <div className="space-y-3">
            {biz.services.filter((s) => s.category === cat).map((s) => (
              <button key={s.id} onClick={() => go({ service: s.id, staff: null, date: null, time: null })}
                className="flex w-full items-center gap-3 rounded-2xl border border-line bg-white p-3 text-left raise active:bg-brand-50">
                <CategoryTile category={s.category} size={48} />
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold">{s.name}</span>
                  <span className="text-sm text-stone-500">{s.duration_min} min · {inr(s.price_paise)} <span className="text-xs">incl. GST</span></span>
                </span>
                <span className="shrink-0 rounded-full bg-gold px-2.5 py-1 text-xs font-bold text-brand-900">{inr(advancePaise(s))} advance</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {step === "stylist" && service && (
        <section className="animate-step">
          <h2 className="mb-3 text-lg font-semibold">Choose a stylist</h2>
          {stylists.length === 0 ? <Skeleton /> : (
            <div className="space-y-3">
              <StylistCard name="Any available" sub="Fastest option" next={stylists.map((s) => s.next_free).filter(Boolean).sort()[0] ?? null}
                onClick={() => go({ staff: "any", date: null, time: null })} />
              {stylists.map((s) => (
                <StylistCard key={s.id} name={s.name} sub={s.title} next={s.next_free} onClick={() => go({ staff: s.id, date: null, time: null })} />
              ))}
            </div>
          )}
        </section>
      )}

      {step === "time" && service && (
        <section className="animate-step">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Pick a date &amp; time</h2>
            <p className="flex flex-wrap items-center gap-2 text-xs font-semibold text-brand-800">
              <span className="rounded-full bg-brand-100 px-2.5 py-1">{service.name}</span>
              <span className="rounded-full bg-brand-100 px-2.5 py-1">{staffId === "any" ? "Any available stylist" : stylists.find((x) => x.id === staffId)?.name ?? "Stylist"}</span>
            </p>
          </div>
          <div className="md:grid md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] md:items-start md:gap-8">
            <div className="rounded-3xl border border-line bg-white p-3 shadow-[0_12px_32px_-18px_rgba(2,132,199,0.35)] sm:p-4">
              <MonthCalendar days={days} selected={date} onPick={(d) => go({ date: d, time: null })} />
            </div>
            <div className="mt-4 md:mt-0" aria-live="polite">
              {!date ? (
                <div className="flex min-h-[200px] flex-col items-center justify-center rounded-3xl border border-dashed border-brand-200 bg-white/60 p-6 text-center">
                  <span className="mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-2xl text-brand-700">◷</span>
                  <p className="font-semibold">Choose a day on the calendar</p>
                  <p className="text-sm text-slate-500">Free start times for that day appear here.</p>
                </div>
              ) : (
                <div className="rounded-3xl border border-line bg-white p-4 shadow-[0_12px_32px_-18px_rgba(2,132,199,0.35)]">
                  <div className="mb-3 flex items-end justify-between gap-2">
                    <h3 className="text-lg font-extrabold tracking-tight">{fmtDay(date, { weekday: "long", day: "numeric", month: "long" })}</h3>
                    {!loadingSlots && <span className="text-xs font-medium text-slate-500">{flat(slots).length} times · IST</span>}
                  </div>
                  {loadingSlots ? <Skeleton /> : flat(slots).length === 0 ? (
                    <NoSlots days={days} date={date} onPick={(d) => go({ date: d, time: null })} />
                  ) : (
                    (["morning", "afternoon", "evening"] as const).map((g) => {
                      const items = [...slots[g], ...goneSlots.filter((p) => !slots[g].some((s) => s.start === p.start) && groupOf(p.start) === g)]
                        .sort((a, b) => a.start.localeCompare(b.start));
                      return items.length ? (
                        <div key={g} className="mb-4 last:mb-0">
                          <h4 className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-brand-600">{g}</h4>
                          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                            {items.map((s) => (
                              <button key={s.start} disabled={gone.has(s.start)} onClick={() => go({ time: s.start })}
                                className={`raise rounded-xl border border-line bg-white px-2 py-2.5 text-sm font-semibold transition-opacity duration-500 hover:border-brand-400 hover:bg-brand-50 ${gone.has(s.start) ? "line-through opacity-30" : ""}`}>{fmtTime(s.start)}</button>
                            ))}
                          </div>
                        </div>
                      ) : null;
                    })
                  )}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {step === "details" && service && time && (
        <Details biz={biz} service={service} staffId={staffId!} time={time} date={date!}
          onHold={(h) => {
            if (h.status === "confirmed") { router.push(`/b/${slug}/confirm/${h.public_token}`); return; }
            setHold(h); try { sessionStorage.setItem(`hold:${slug}`, JSON.stringify(h)); } catch { /* */ }
          }}
          onTaken={(msg) => { setNotice(msg); go({ time: null }); }} onError={fail} />
      )}

      {step === "held" && service && time && hold && (
        <section className="animate-step space-y-4">
          {expired ? (
            <>
              <Banner tone="warn">Your slot hold expired. Please choose a time again.</Banner>
              <button className={btn} onClick={() => { clearHold(); go({ time: null }); }}>Pick another time</button>
            </>
          ) : (
            <>
              <div className="rounded-2xl bg-emerald-50 p-4 text-emerald-900 ring-1 ring-emerald-200">
                <p className="font-semibold">Slot held for {mmss(left)}</p>
                <p className="text-sm">{service.name} · {fmtDay(time)} · {fmtTime(time)}</p>
              </div>
              <Pay biz={biz} service={service} hold={hold} left={left}
                onPaid={(tok) => router.push(`/b/${slug}/confirm/${tok}`)}
                onDismiss={async () => { await release(); setNotice("Payment was cancelled and your slot was released."); go({ time: null }); }} />
            </>
          )}
        </section>
      )}
      <Footer slug={slug} />
    </Shell>
  );
}

declare global {
  interface Window { Razorpay?: new (o: Record<string, unknown>) => { open: () => void; on: (e: string, cb: (r: { error?: { description?: string } }) => void) => void } }
}

function Pay({ biz, service, hold, left, onPaid, onDismiss }: {
  biz: Business; service: Service; hold: Hold; left: number; onPaid: (token: string) => void; onDismiss: () => void;
}) {
  const [ready, setReady] = useState(typeof window !== "undefined" && !!window.Razorpay);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const paid = useRef(false);
  const order = hold.order;
  const mock = order?.key_id === "rzp_mock"; // prototype: no Razorpay keys, simulated checkout
  const [mockOpen, setMockOpen] = useState(false);

  // Checkout.js is loaded only on this step.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (mock || window.Razorpay) { setReady(true); return; }
    const sc = document.createElement("script");
    sc.src = "https://checkout.razorpay.com/v1/checkout.js";
    sc.async = true;
    sc.onload = () => setReady(true);
    sc.onerror = () => setFailure("Couldn't load the payment window. Check your connection and retry.");
    document.body.appendChild(sc);
  }, [mock]);

  function open() {
    if (mock) { setMockOpen(true); setFailure(null); return; }
    if (!order || !window.Razorpay || busy) return;
    setBusy(true);
    setFailure(null);
    const rz = new window.Razorpay({
      key: order.key_id, order_id: order.order_id, amount: order.amount_paise, currency: "INR",
      name: biz.name, description: service.name, theme: { color: "#0284c7" },
      prefill: { name: hold.name, contact: hold.phone ? `+91${hold.phone}` : undefined },
      timeout: Math.max(60, Math.min(540, Math.floor(left / 1000) - 20)), retry: { enabled: true },
      config: { display: { preferences: { show_default_blocks: true } } },
      modal: { ondismiss: () => { setBusy(false); if (!paid.current) onDismiss(); } },
      handler: async (resp: Record<string, string>) => {
        paid.current = true;
        try {
          await api("/public/payments/verify", { method: "POST", body: JSON.stringify(resp) });
        } catch { /* the confirmation page keeps polling; the webhook may confirm */ }
        onPaid(hold.public_token);
      },
    });
    rz.on("payment.failed", (r) => { setBusy(false); setFailure(r.error?.description ?? "Payment didn't go through. You can try again."); });
    rz.open();
    api(`/public/holds/${hold.booking_id}/checkout-opened`, { method: "POST", body: JSON.stringify({ public_token: hold.public_token }) }).catch(() => {});
  }

  if (!order) return null;
  const adv = order.amount_paise;
  return (
    <div className="space-y-4">
      <Summary service={service} />
      {failure && <Banner tone="error">{failure}</Banner>}
      {mockOpen && order && (
        <MockCheckout biz={biz} service={service} hold={hold} amount={adv0(order)} onClose={() => { setMockOpen(false); onDismiss(); }}
          onPaid={() => { paid.current = true; setMockOpen(false); onPaid(hold.public_token); }} />
      )}
      <button className={btn} disabled={!ready || busy} onClick={open}>{busy ? "Opening payment…" : `Pay ${inr(adv)} advance`}</button>
      <p className="text-center text-xs text-stone-500">
        By paying you agree to our <a className="underline" href={`/b/${biz.slug}/terms`}>Terms</a> and <a className="underline" href={`/b/${biz.slug}/refund`}>Refund &amp; Cancellation</a> policy.
        {order.key_id.startsWith("rzp_test") && <span className="ml-1 rounded bg-stone-200 px-1.5 py-0.5 text-[10px] font-medium">Test mode</span>}
        {mock && <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">Simulated payment · prototype</span>}
      </p>
      <button className="w-full py-2 text-sm text-stone-600 underline" onClick={onDismiss}>Choose another time</button>
    </div>
  );
}

const adv0 = (o: { amount_paise: number }) => o.amount_paise;

/** Prototype-only checkout that mimics Razorpay's test UPI flow (success@razorpay / failure@razorpay). */
function MockCheckout({ biz, service, hold, amount, onClose, onPaid }: {
  biz: Business; service: Service; hold: Hold; amount: number; onClose: () => void; onPaid: () => void;
}) {
  const [upi, setUpi] = useState("success@razorpay");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function pay() {
    if (busy || !hold.order) return;
    setBusy(true); setErr(null);
    try {
      await api("/prototype/pay", { method: "POST", body: JSON.stringify({ order_id: hold.order.order_id, upi }) });
      onPaid();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Payment failed"); } finally { setBusy(false); }
  }
  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-brand-900/50 sm:items-center" role="dialog" aria-label="Simulated checkout">
      <div className="animate-step w-full max-w-sm overflow-hidden rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl">
        <div className="bg-brand-700 px-5 py-4 text-white">
          <div className="flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wider opacity-80">Razorpay Checkout · test (simulated)</p>
            <button onClick={onClose} aria-label="Close checkout" className="text-2xl leading-none opacity-80">×</button></div>
          <p className="mt-1 text-lg font-bold">{biz.name}</p>
          <p className="text-sm opacity-90">{service.name}</p>
          <p className="mt-2 text-3xl font-extrabold tracking-tight">{inr(amount)}</p>
        </div>
        <div className="space-y-3 p-5">
          <label className="block text-sm font-semibold text-brand-900">Pay with UPI
            <input value={upi} onChange={(e) => setUpi(e.target.value)} aria-label="UPI ID" className="mt-1 w-full rounded-xl border border-line bg-brand-50 p-3 font-mono text-sm" />
          </label>
          <p className="text-xs text-stone-500">Prototype only, no real money moves. Use <b>success@razorpay</b> to pay, or <b>failure@razorpay</b> to see the retry state.</p>
          {err && <p role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-800">{err}</p>}
          <button className={btn} disabled={busy || !upi.trim()} onClick={pay}>{busy ? "Processing…" : `Pay ${inr(amount)}`}</button>
        </div>
      </div>
    </div>
  );
}

function groupOf(iso: string) {
  const h = Number(new Date(iso).toLocaleString("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", hour12: false }));
  return h < 12 ? "morning" : h < 17 ? "afternoon" : "evening";
}

function Shell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return <main className={`mx-auto min-h-screen overflow-x-hidden bg-cream px-4 pt-4 text-brand-900 ${process.env.NEXT_PUBLIC_PROTOTYPE === "1" ? "pb-24" : "pb-10"} ${wide ? "max-w-md md:max-w-5xl" : "max-w-md"}`}>{children}</main>;
}

function Header({ biz }: { biz: Business }) {
  const close = biz.closes_at ? fmtTime(biz.closes_at) : null;
  const chip = "flex-1 rounded-xl border border-line bg-white py-2.5 text-center text-sm font-semibold active:scale-[0.98]";
  return (
    <header className="mb-5 rounded-3xl border border-line bg-brand-100 p-4">
      <div className="flex items-start gap-3">
        <LogoMark className="h-12 w-12 shrink-0" />
        <div className="min-w-0">
          <h1 className="tracking-tight text-xl font-bold leading-tight">{biz.name}</h1>
          <p className="text-sm text-stone-700">{biz.address}</p>
        </div>
      </div>
      <p className="mt-3 inline-flex items-center gap-2 rounded-full border border-line bg-gold px-3 py-1 text-xs font-bold uppercase tracking-wide">
        <span className={`h-2 w-2 rounded-full ${biz.open_now ? "bg-emerald-600" : "bg-stone-500"}`} />{biz.open_now && close ? `Open now · closes ${close}` : "Closed right now"}
      </p>
      <div className="mt-3 flex gap-2">
        <a href={`tel:${biz.phone.replace(/\s/g, "")}`} className={chip}>Call</a>
        <a href={biz.maps_url} target="_blank" rel="noreferrer" className={chip}>Directions</a>
      </div>
    </header>
  );
}

function Banner({ tone, children }: { tone: "error" | "warn"; children: React.ReactNode }) {
  return <div role="alert" className={`mb-3 rounded-xl p-3 text-sm ${tone === "error" ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-900"}`}>{children}</div>;
}

const Skeleton = () => <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-stone-200" />)}</div>;

function StylistCard({ name, sub, next, onClick }: { name: string; sub: string; next: string | null; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex w-full items-center gap-3 rounded-2xl border border-line bg-white p-3 text-left raise active:bg-brand-50">
      {(() => { const a = STYLISTS.find((x) => x.name === name); return a ? <Avatar {...a.art} className="h-12 w-12 shrink-0" /> : <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-line bg-gold font-bold">{name[0]}</span>; })()}
      <span className="flex-1">
        <span className="block font-medium">{name}</span>
        <span className="text-sm text-stone-500">{sub}</span>
      </span>
      <span className="text-right text-xs text-emerald-700">{next ? <>Next free:<br />{fmtDay(next, { weekday: "short" })} {fmtTime(next)}</> : "No openings"}</span>
    </button>
  );
}

function NoSlots({ days, date, onPick }: { days: Day[]; date: string; onPick: (d: string) => void }) {
  const next = days.find((d) => d.date > date && !d.full);
  return (
    <div className="rounded-2xl border border-line bg-white p-5 text-center">
      <p className="font-medium">No times left on this day</p>
      {next ? <button className="mt-3 text-brand-700 underline" onClick={() => onPick(next.date)}>Try {fmtDay(next.date)} instead</button>
        : <p className="mt-1 text-sm text-stone-500">Please check another day.</p>}
    </div>
  );
}

function Summary({ service }: { service: Service }) {
  const adv = advancePaise(service);
  return (
    <div className="rounded-2xl bg-white p-4 text-sm ring-1 ring-stone-200">
      <Row k={service.name} v={`${inr(service.price_paise)} incl. GST`} />
      <Row k="Advance now" v={inr(adv)} bold />
      <Row k="Balance at the salon" v={inr(service.price_paise - adv)} />
    </div>
  );
}
const Row = ({ k, v, bold }: { k: string; v: string; bold?: boolean }) => (
  <div className={`flex justify-between py-1 ${bold ? "font-semibold" : ""}`}><span>{k}</span><span>{v}</span></div>
);

function Details({ biz, service, staffId, time, date, onHold, onTaken, onError }: {
  biz: Business; service: Service; staffId: string; time: string; date: string;
  onHold: (h: Hold) => void; onTaken: (m: string) => void; onError: (e: unknown) => void;
}) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [wa, setWa] = useState(true);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const valid = name.trim().length > 0 && /^[6-9]\d{9}$/.test(phone) && agree;
  const phoneBad = phone.length > 0 && !/^[6-9]\d{9}$/.test(phone);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    try {
      const h = await api<Hold>(`/public/${biz.slug}/holds`, {
        method: "POST",
        body: JSON.stringify({ service_id: service.id, staff_id: staffId === "any" ? null : staffId, start: time, name, phone, whatsapp_opt_in: wa, policy_accepted: agree }),
      });
      onHold({ ...h, name: name.trim(), phone });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) onTaken(`${fmtTime(time)} on ${fmtDay(date)} was just taken. Please pick another time.`);
      else onError(err);
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="animate-step space-y-4">
      <h2 className="text-lg font-semibold">Your details</h2>
      <div className="rounded-xl bg-white p-3 text-sm ring-1 ring-stone-200">{service.name} · {fmtDay(time)} · {fmtTime(time)}</div>
      <input aria-label="Full name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" autoComplete="name"
        className="w-full rounded-xl bg-white p-4 ring-1 ring-stone-300" />
      <div>
        <div className="flex items-center rounded-xl bg-white ring-1 ring-stone-300">
          <span className="border-r px-4 py-4 text-stone-600">+91</span>
          <input aria-label="Mobile number" inputMode="numeric" maxLength={10} value={phone} autoComplete="tel-national"
            onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} placeholder="10-digit mobile number" className="w-full rounded-xl p-4 outline-none" />
        </div>
        {phoneBad && <p className="mt-1 text-xs text-red-700">Enter a valid 10-digit mobile number</p>}
      </div>
      <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={wa} onChange={(e) => setWa(e.target.checked)} className="mt-1 h-5 w-5" />Send booking updates on WhatsApp</label>
      <div className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
        <p className="font-medium">Cancellation policy</p>
        <p>{biz.policy_text || `Free cancellation up to ${biz.cancellation_cutoff_hours} hours before your appointment. Later cancellations forfeit the advance.`}</p>
      </div>
      <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1 h-5 w-5" />I agree to the cancellation policy</label>
      <Summary service={service} />
      <button className={btn} disabled={!valid || busy}>{busy ? "Holding your slot…" : "Hold my slot"}</button>
    </form>
  );
}

function Footer({ slug }: { slug: string }) {
  return (
    <footer className="mt-10 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-stone-500">
      {["terms", "privacy", "refund", "contact"].map((p) => <a key={p} href={`/b/${slug}/${p}`} className="capitalize underline">{p === "refund" ? "Refund & Cancellation" : p}</a>)}
    </footer>
  );
}
