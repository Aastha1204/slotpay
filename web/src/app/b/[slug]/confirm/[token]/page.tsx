"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError, BookingView, api, fmtDay, fmtTime, inr } from "@/lib/booking";
import { API_BASE } from "@/lib/supabase";
import { Confetti } from "@/components/motion";
import PhoneInbox from "@/components/PhoneInbox";
import { PROTOTYPE } from "@/lib/prototype";

const POLL_MS = 2000;
const POLL_LIMIT_MS = 30000;

export default function Page() {
  return (
    <Suspense fallback={<div className="p-6 text-stone-500">Loading…</div>}>
      <Confirm />
    </Suspense>
  );
}

function Confirm() {
  const { slug, token } = useParams<{ slug: string; token: string }>();
  const [b, setB] = useState<BookingView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const started = useRef(0);
  const statusRef = useRef("held");

  const load = useCallback(async () => {
    try {
      const v = await api<BookingView>(`/public/bookings/${token}`);
      statusRef.current = v.status;
      setB(v);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "We couldn't find this booking." : "We couldn't reach the server. Retrying…");
    }
  }, [token]);

  useEffect(() => {
    started.current = Date.now();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    const t = setInterval(() => {
      if (statusRef.current === "held" && Date.now() - started.current > POLL_LIMIT_MS) { setTimedOut(true); clearInterval(t); return; }
      if (statusRef.current !== "held" && !PROTOTYPE) { clearInterval(t); return; }
      load();
    }, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  const pending = !b || b.status === "held";
  return (
    <main className={`mx-auto min-h-screen overflow-x-hidden bg-cream px-4 pb-10 pt-8 text-brand-900 ${PROTOTYPE ? "max-w-md md:max-w-5xl" : "max-w-md"}`}>
      <div className={PROTOTYPE ? "md:grid md:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] md:items-start md:gap-10" : ""}>
      <div>
      {error && !b && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}

      {pending && !error && !timedOut && (
        <div className="py-16 text-center" aria-live="polite">
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-brand-200 border-t-brand-700" />
          <p className="font-medium">Confirming your payment…</p>
          <p className="text-sm text-stone-500">This usually takes a few seconds. Please don&apos;t close this page.</p>
        </div>
      )}

      {pending && timedOut && (
        <div className="rounded-2xl bg-amber-50 p-5 text-amber-900">
          <p className="font-semibold">We&apos;re still confirming your payment</p>
          <p className="mt-1 text-sm">If money was deducted, your booking will be confirmed shortly or refunded automatically.</p>
          <button className="mt-3 rounded-xl bg-white px-4 py-3 text-sm font-medium ring-1 ring-amber-300"
            onClick={() => { started.current = Date.now(); setTimedOut(false); load(); }}>Check again</button>
        </div>
      )}

      {b?.status === "confirmed" && <Success b={b} token={token} />}

      {b && (b.status === "expired" || b.status === "cancelled") && (
        <div className="rounded-2xl bg-white p-5 ring-1 ring-stone-200">
          <p className="font-semibold">This slot is no longer available</p>
          <p className="mt-1 text-sm text-stone-600">
            {b.payment_status === "refunded" || b.refunded_paise > 0
              ? `Your payment of ${inr(b.refunded_paise)} is being refunded to the original method.`
              : "No payment was taken for this booking."}
          </p>
          <a href={`/b/${slug}`} className="mt-4 block rounded-2xl bg-brand-700 px-5 py-4 text-center font-semibold text-white">Book another time</a>
        </div>
      )}
      </div>
      {PROTOTYPE && b && b.status !== "held" && (
        <div className="mt-8 md:sticky md:top-6 md:mt-0"><PhoneInbox token={token} onChange={load} /></div>
      )}
      </div>
    </main>
  );
}

function Success({ b, token }: { b: BookingView; token: string }) {
  return (
    <div className="animate-step relative space-y-5">
      <Confetti />
      <div className="text-center">
        <div className="mx-auto mb-3 flex h-16 w-16 animate-[pop_.4s_ease-out] items-center justify-center rounded-full bg-emerald-100 text-3xl text-emerald-700">✓</div>
        <h1 className="tracking-tight text-2xl font-semibold">You&apos;re booked, {b.customer_first_name}!</h1>
        <p className="text-sm text-stone-600">Booking ID <span className="font-mono">{b.booking_id.slice(0, 8).toUpperCase()}</span></p>
      </div>
      <div className="space-y-1 rounded-2xl bg-white p-4 text-sm ring-1 ring-stone-200">
        <Row k="Service" v={b.service} />
        <Row k="Stylist" v={b.stylist} />
        <Row k="When" v={`${fmtDay(b.start, { weekday: "short", day: "numeric", month: "short" })} · ${fmtTime(b.start)}`} />
        <Row k="Advance paid" v={inr(b.advance_paid_paise)} />
        <Row k="Balance at the salon" v={inr(b.balance_paise)} bold />
      </div>
      <div className="rounded-xl bg-white p-3 text-sm ring-1 ring-stone-200">
        <p className="font-medium">{b.business.name}</p>
        <p className="text-stone-600">{b.business.address}</p>
        <div className="mt-2 flex gap-4">
          <a href={b.business.maps_url} target="_blank" rel="noreferrer" className="text-brand-700 underline">Get directions</a>
          <a href={`${API_BASE}/public/bookings/${token}/ics`} className="text-brand-700 underline">Add to calendar</a>
        </div>
      </div>
      {b.whatsapp_sent && <p className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">WhatsApp confirmation sent to {b.masked_phone}</p>}
      <p className="text-xs text-stone-500">Free cancellation up to {b.cancellation_cutoff_hours} hours before your appointment. Later cancellations forfeit the advance.</p>
    </div>
  );
}

const Row = ({ k, v, bold }: { k: string; v: string; bold?: boolean }) => (
  <div className={`flex justify-between gap-3 py-0.5 ${bold ? "font-semibold" : ""}`}><span className="text-stone-500">{k}</span><span className="text-right">{v}</span></div>
);
