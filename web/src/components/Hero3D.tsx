"use client";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

// three.js is only fetched here, after the page has loaded and the browser is idle, so first paint stays fast.
const HeroScene = dynamic(() => import("./HeroScene"), { ssr: false });

type IdleWindow = Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number };

function webglOk(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch { return false; }
}

/** Shows the SVG illustration immediately, then crossfades to the live 3D scene when it is ready. */
export default function Hero3D({ children }: { children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const nav = navigator as Navigator & { connection?: { saveData?: boolean }; deviceMemory?: number };
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const weak = (nav.hardwareConcurrency ?? 4) <= 2 || !!nav.connection?.saveData || (nav.deviceMemory ?? 4) <= 2;
    if (reduce || weak || !webglOk()) return; // keep the static illustration
    // Start on the first interaction, or after 5 s, whichever comes first. The static hero is already
    // on screen, so there is nothing to wait for, and the heavy three.js init never competes with page load.
    let started = false;
    let timer: number | undefined;
    const events = ["pointerdown", "pointermove", "scroll", "keydown", "touchstart"] as const;
    const start = () => setEnabled(true);
    const fire = () => {
      if (started) return;
      started = true;
      events.forEach((e) => window.removeEventListener(e, fire));
      window.clearTimeout(timer);
      const w = window as IdleWindow;
      if (w.requestIdleCallback) w.requestIdleCallback(start, { timeout: 1500 });
      else window.setTimeout(start, 200);
    };
    const arm = () => {
      events.forEach((e) => window.addEventListener(e, fire, { passive: true, once: true }));
      timer = window.setTimeout(fire, 5000);
    };
    if (document.readyState === "complete") arm();
    else window.addEventListener("load", arm, { once: true });
    return () => {
      started = true;
      window.clearTimeout(timer);
      window.removeEventListener("load", arm);
      events.forEach((e) => window.removeEventListener(e, fire));
    };
  }, []);

  useEffect(() => {
    const el = box.current;
    if (!el || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.05 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={box} className="relative mx-auto aspect-[1/0.9] w-full max-w-[560px]" data-testid="hero-3d" data-3d={ready ? "on" : "off"}>
      <div className={`absolute inset-0 transition-opacity duration-700 ${ready ? "pointer-events-none opacity-0" : "opacity-100"}`}>{children}</div>
      {enabled && (
        <div className={`absolute inset-0 transition-opacity duration-700 ${ready ? "opacity-100" : "opacity-0"}`} role="img" aria-label="3D illustration of a salon mirror, chair and scissors">
          <HeroScene active={visible} onReady={() => setReady(true)} />
        </div>
      )}
      {ready && (
        <>
          <div className="animate-float pointer-events-none absolute left-0 top-[8%] flex items-center gap-2 rounded-2xl border border-line bg-white px-3 py-2 text-sm font-bold shadow-[0_12px_32px_-16px_rgba(2,132,199,0.40)]">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-sage text-brand-700">✓</span>Booked · Sat 4:00 PM
          </div>
          <div className="animate-float pointer-events-none absolute bottom-[8%] right-0 flex items-center gap-2 rounded-2xl border border-line bg-brand-700 px-3 py-2 text-sm font-bold text-white shadow-[0_10px_22px_-8px_rgba(2,132,199,0.60)] [animation-delay:-2s]">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gold text-brand-900">₹</span>200 advance paid
          </div>
        </>
      )}
    </div>
  );
}
