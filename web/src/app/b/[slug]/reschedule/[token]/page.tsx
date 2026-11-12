"use client";
import { Suspense, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BookingView, api, fmtDay, fmtTime } from "@/lib/booking";

export default function Page() {
  return (
    <Suspense fallback={<div className="p-6 text-stone-500">Loading…</div>}>
      <Reschedule />
    </Suspense>
  );
}

// Self-serve rescheduling arrives with the admin calendar (M6). Until then this page shows the booking
// and the salon's contact details so the link in WhatsApp never dead-ends.
function Reschedule() {
  const { slug, token } = useParams<{ slug: string; token: string }>();
  const [b, setB] = useState<BookingView | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { api<BookingView>(`/public/bookings/${token}`).then(setB).catch(() => setErr(true)); }, [token]);
  return (
    <main className="mx-auto min-h-screen max-w-md bg-cream px-4 pt-8 text-brand-900">
      <h1 className="tracking-tight text-2xl font-semibold">Reschedule your visit</h1>
      {err && <p className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-800">We couldn&apos;t find this booking.</p>}
      {b && (
        <div className="mt-4 space-y-3">
          <div className="rounded-2xl bg-white p-4 text-sm ring-1 ring-stone-200">
            <p className="font-medium">{b.service} with {b.stylist}</p>
            <p>{fmtDay(b.start)} · {fmtTime(b.start)}</p>
          </div>
          <p className="text-sm text-stone-600">Online rescheduling is coming soon. To move your appointment, please call {b.business.name} and we&apos;ll sort it out, your advance carries over.</p>
          <a href={`/b/${slug}`} className="block rounded-2xl bg-white py-4 text-center font-medium ring-1 ring-stone-300">Back to booking page</a>
        </div>
      )}
    </main>
  );
}
