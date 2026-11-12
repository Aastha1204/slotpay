"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { DEMO_KEY } from "@/lib/prototype";
import { API_BASE } from "@/lib/supabase";

type Msg = { id: string; direction: "in" | "out"; body: string; buttons: { text: string; payload: string }[] | null; at: string };

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", hour12: true }).toLowerCase();

export default function Page() {
  return (
    <Suspense fallback={<div className="p-6 text-stone-500">Loading…</div>}>
      <Simulator />
    </Suspense>
  );
}

function Simulator() {
  const sp = useSearchParams();
  const phone = sp.get("phone") ?? "";
  const key = sp.get("key") || DEMO_KEY;
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [name, setName] = useState("Glow Studio Salon & Spa");
  const [error, setError] = useState<string | null>(null);
  const [pressed, setPressed] = useState<Set<string>>(new Set());
  const end = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!phone) return;
    try {
      const r = await fetch(`${API_BASE}/demo/whatsapp/messages?phone=${encodeURIComponent(phone)}&key=${encodeURIComponent(key)}`);
      if (r.status === 403) { setError("Demo key required or incorrect."); return; }
      const j = await r.json();
      setMsgs(j.messages); setName(j.business); setError(null);
    } catch { setError("Can't reach the server."); }
  }, [phone, key]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); const t = setInterval(load, 2000); return () => clearInterval(t); }, [load]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length]);

  async function press(b: { text: string; payload: string }) {
    if (pressed.has(b.payload)) return;
    setPressed((s) => new Set(s).add(b.payload));
    await fetch(`${API_BASE}/demo/whatsapp/button?key=${encodeURIComponent(key)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ phone, payload: b.payload, text: b.text }),
    });
    load();
  }

  return (
    <main className="mx-auto flex h-screen max-w-md flex-col bg-[#e5ddd5]">
      <header className="flex items-center gap-3 bg-[#075e54] px-4 py-3 text-white">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-200 font-semibold text-brand-900">
          {name.split(" ").slice(0, 2).map((w) => w[0]).join("")}
        </div>
        <div><p className="font-medium leading-tight">{name}</p><p className="text-xs opacity-80">Business account · +91 {phone.slice(-10)}</p></div>
      </header>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {error && <p className="rounded bg-white p-3 text-sm text-red-700">{error}</p>}
        {!error && msgs.length === 0 && <p className="mt-10 text-center text-sm text-stone-600">No messages yet for this number.</p>}
        {msgs.map((m) => (
          <div key={m.id} className={`flex ${m.direction === "out" ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm shadow ${m.direction === "out" ? "bg-white" : "bg-[#dcf8c6]"}`}>
              <p className="whitespace-pre-wrap">{m.body}</p>
              <p className="mt-1 text-right text-[10px] text-stone-500">{time(m.at)}{m.direction === "in" && " ✓✓"}</p>
              {m.buttons && m.buttons.length > 0 && (
                <div className="mt-2 space-y-1 border-t pt-2">
                  {m.buttons.map((b) => (
                    <button key={b.payload} onClick={() => press(b)} disabled={pressed.has(b.payload)}
                      className="w-full rounded bg-stone-50 py-2 text-center font-medium text-sky-700 disabled:opacity-50">{b.text}</button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
    </main>
  );
}
