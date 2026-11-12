import { Suspense } from "react";
import CalendarView from "./Calendar";

export const metadata = { title: "Admin · Glow Studio" };

export default function Page() {
  return (
    <Suspense fallback={<div className="p-6 text-stone-500">Loading…</div>}>
      <CalendarView />
    </Suspense>
  );
}
