"use client";
import { useEffect, useRef } from "react";

const reduced = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Fades/tilts children in as they scroll into view. Content stays visible without JS and for anything already on screen. */
export function Reveal({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced() || !("IntersectionObserver" in window)) return;
    if (el.getBoundingClientRect().top < window.innerHeight * 0.92) return; // already in view: don't hide it
    el.style.setProperty("--d", `${delay}ms`);
    el.classList.add("reveal");
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { el.classList.add("reveal-in"); io.disconnect(); }
    }, { threshold: 0.12 });
    io.observe(el);
    return () => io.disconnect();
  }, [delay]);
  return <div ref={ref} className={className}>{children}</div>;
}

/** Mouse-driven 3D tilt (desktop only; touch and reduced-motion are left alone). */
export function Tilt({ children, className = "", max = 9 }: { children: React.ReactNode; className?: string; max?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el || e.pointerType !== "mouse" || reduced()) return;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(800px) rotateX(${(-y * max).toFixed(2)}deg) rotateY(${(x * max).toFixed(2)}deg) translateZ(8px)`;
  };
  const leave = () => { if (ref.current) ref.current.style.transform = ""; };
  return (
    <div ref={ref} onPointerMove={move} onPointerLeave={leave} className={`transition-transform duration-200 ease-out will-change-transform ${className}`}>
      {children}
    </div>
  );
}

/** Infinite scrolling text band. */
export function Marquee({ items, className = "" }: { items: string[]; className?: string }) {
  const row = [...items, ...items];
  return (
    <div className={`overflow-hidden ${className}`} aria-hidden>
      <div className="animate-marquee flex w-max gap-10 whitespace-nowrap">
        {[0, 1].map((k) => (
          <div key={k} className="flex shrink-0 gap-10">
            {row.map((t, i) => <span key={i} className="flex items-center gap-10">{t}<span className="text-lg">✦</span></span>)}
          </div>
        ))}
      </div>
    </div>
  );
}

const PIECES = Array.from({ length: 26 }, (_, i) => ({
  left: (i * 37) % 100, dx: ((i * 53) % 120) - 60, delay: (i % 9) * 0.07, dur: 1.6 + (i % 5) * 0.25, color: ["#0284c7", "#fcd34d", "#38bdf8", "#ec6ea8", "#a78bfa"][i % 5], w: 7 + (i % 3) * 3,
}));

/** One-shot celebratory burst (CSS 3D flips). */
export function Confetti() {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 h-0" aria-hidden>
      {PIECES.map((p, i) => (
        <span key={i} className="animate-confetti absolute block rounded-[2px]"
          style={{ left: `${p.left}%`, width: p.w, height: p.w * 1.6, background: p.color, animationDelay: `${p.delay}s`, animationDuration: `${p.dur}s`, ["--dx" as string]: `${p.dx}px` }} />
      ))}
    </div>
  );
}
