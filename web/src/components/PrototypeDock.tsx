"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/supabase";
import { DEMO_KEY, Role, currentRole, switchRole } from "@/lib/prototype";
import { surfaces } from "@/lib/surfaces";

/** Floating launcher shown on every page in prototype mode: jump anywhere, switch staff role. */
export default function PrototypeDock() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState<Role>(() => currentRole());
  const [phone, setPhone] = useState<string | null>(null);

  useEffect(() => {
    if (!open || phone) return;
    fetch(`${API_BASE}/prototype/summary`).then((r) => (r.ok ? r.json() : null)).then((j) => { if (j?.latest_phone) setPhone(j.latest_phone); }).catch(() => {});
  }, [open, phone]);

  async function pick(r: Role) {
    if (await switchRole(r)) {
      setRole(r);
      if (path.startsWith("/admin")) window.location.reload();
    }
  }

  const groups = surfaces(DEMO_KEY, phone);
  const active = (href: string) => href.split("?")[0] === path;

  return (
    <div className="fixed bottom-4 left-4 z-[60] font-sans text-brand-900">
      {open && (
        <div role="dialog" aria-label="Prototype navigation" className="glass animate-step mb-3 max-h-[75vh] w-[min(92vw,22rem)] overflow-y-auto rounded-3xl p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="font-bold tracking-tight">SlotPay prototype</p>
            <Link href="/prototype" onClick={() => setOpen(false)} className="text-sm font-semibold text-brand-700 underline">Open hub</Link>
          </div>
          {groups.map((g) => (
            <div key={g.name} className="mb-3">
              <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.18em] text-brand-600">{g.name}</p>
              <ul className="space-y-1">
                {g.items.map((s) => (
                  <li key={s.title}>
                    <Link href={s.href} onClick={() => setOpen(false)}
                      className={`flex items-center gap-3 rounded-2xl px-2.5 py-2 text-sm font-semibold transition hover:bg-brand-50 ${active(s.href) ? "bg-brand-100 text-brand-800" : ""}`}>
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-100 text-xs font-bold text-brand-700">{s.initial}</span>
                      <span className="min-w-0"><span className="block truncate">{s.title}</span><span className="block truncate text-[11px] font-medium text-slate-500">{s.tag}</span></span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <div className="rounded-2xl bg-brand-50 p-3">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-brand-600">Staff login as</p>
            <div className="grid grid-cols-2 gap-2">
              {(["owner", "front_desk"] as const).map((r) => (
                <button key={r} onClick={() => pick(r)} aria-pressed={role === r}
                  className={`rounded-xl py-2 text-sm font-semibold ${role === r ? "bg-brand-700 text-white" : "bg-white ring-1 ring-brand-200"}`}>{r === "owner" ? "Owner" : "Front desk"}</button>
              ))}
            </div>
          </div>
        </div>
      )}
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="glass flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-bold text-brand-800 transition hover:-translate-y-0.5">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-[11px] text-white">{open ? "×" : "◧"}</span>
        Prototype
      </button>
    </div>
  );
}
