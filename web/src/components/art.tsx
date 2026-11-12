// Flat 2D illustration kit: solid fills, simple geometry, one shared palette. No gradients, no external assets.
import type { SVGProps } from "react";

export const C = {
  // "rose*" keys are the brand colour (kept for call-site stability). Keep in sync with --color-* in globals.css.
  rose: "#0284c7", roseDark: "#0369a1", rose100: "#e0f2fe", rose200: "#bae6fd", cream: "#f8fbff", ink: "#2c5a84",
  amber: "#fcd34d", amber100: "#fef3c7", teal: "#2f9e8f", teal100: "#d9f4ef", peach: "#fdba74", plum: "#ec6ea8", plum100: "#fce7f3",
  white: "#ffffff", stone: "#e2e8f0",
};

type P = SVGProps<SVGSVGElement>;

export function LogoMark(p: P) {
  return (
    <svg viewBox="0 0 40 40" aria-hidden {...p}>
      <rect width="40" height="40" rx="12" fill={C.rose} />
      <circle cx="20" cy="20" r="9" fill={C.rose100} />
      <path d="M20 8l2.2 6.2L28.5 16l-6.3 1.8L20 24l-2.2-6.2L11.5 16l6.3-1.8z" fill={C.amber} />
    </svg>
  );
}

/** Hero scene: salon mirror, chair, plant, scissors and two floating "app" chips. */
export function HeroArt(p: P) {
  return (
    <svg viewBox="0 0 520 440" role="img" aria-label="Illustration of a salon chair and mirror with a booking confirmed card" {...p}>
      {/* background shapes */}
      <path d="M60 230c0-110 80-190 200-190s210 70 210 180-70 190-200 190S60 340 60 230z" fill={C.rose100} />
      <circle cx="392" cy="88" r="46" fill={C.amber} />
      <circle cx="96" cy="350" r="26" fill={C.teal100} />
      <rect x="40" y="396" width="440" height="14" rx="7" fill={C.rose200} />

      {/* mirror */}
      <rect x="232" y="258" width="16" height="104" fill={C.ink} />
      <rect x="205" y="354" width="70" height="12" rx="6" fill={C.ink} />
      <ellipse cx="240" cy="190" rx="92" ry="118" fill={C.ink} />
      <ellipse cx="240" cy="190" rx="80" ry="106" fill={C.white} />
      <path d="M188 120l40 -28M180 154l66 -46" stroke={C.stone} strokeWidth="10" strokeLinecap="round" />
      <path d="M284 118l4 12 12 4-12 4-4 12-4-12-12-4 12-4z" fill={C.amber} />
      <path d="M200 240l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" fill={C.rose} />

      {/* chair */}
      <g transform="translate(272 268)">
        <rect x="14" y="0" width="82" height="86" rx="22" fill={C.rose} />
        <rect x="0" y="62" width="128" height="34" rx="16" fill={C.roseDark} />
        <rect x="52" y="96" width="24" height="40" fill={C.ink} />
        <rect x="22" y="130" width="84" height="12" rx="6" fill={C.ink} />
        <rect x="104" y="56" width="22" height="12" rx="6" fill={C.ink} />
      </g>

      {/* plant */}
      <g transform="translate(60 276)">
        <path d="M44 120c-30-40-30-76-6-104 6 40 16 66 6 104z" fill={C.teal} />
        <path d="M44 120c30-36 36-70 18-98-10 36-24 62-18 98z" fill="#14b8a6" />
        <path d="M44 120c-12-22-34-30-46-28 14 14 28 22 46 28z" fill={C.teal} />
        <path d="M18 112h52l-8 54H26z" fill={C.amber} />
        <rect x="14" y="106" width="60" height="12" rx="6" fill={C.peach} />
      </g>

      {/* scissors */}
      <g transform="translate(396 232) rotate(-18)">
        <circle cx="12" cy="86" r="14" fill="none" stroke={C.rose} strokeWidth="8" />
        <circle cx="52" cy="86" r="14" fill="none" stroke={C.rose} strokeWidth="8" />
        <path d="M18 74L56 0M46 74L8 0" stroke={C.ink} strokeWidth="9" strokeLinecap="round" />
        <circle cx="32" cy="38" r="5" fill={C.amber} />
      </g>

      {/* floating chips */}
      <g transform="translate(14 74)">
        <rect width="168" height="58" rx="16" fill={C.white} />
        <circle cx="30" cy="29" r="15" fill={C.teal100} />
        <path d="M23 29l5 5 10-11" stroke={C.teal} strokeWidth="4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="54" y="15" width="86" height="9" rx="4.5" fill={C.ink} />
        <rect x="54" y="33" width="60" height="8" rx="4" fill={C.stone} />
      </g>
      <g transform="translate(356 148) scale(0.92)">
        <rect width="150" height="54" rx="16" fill={C.ink} />
        <circle cx="28" cy="27" r="14" fill={C.amber} />
        <text x="28" y="33" textAnchor="middle" fontSize="16" fontWeight="700" fill={C.ink}>₹</text>
        <rect x="52" y="14" width="76" height="9" rx="4.5" fill={C.white} />
        <rect x="52" y="31" width="50" height="8" rx="4" fill="#78716c" />
      </g>
    </svg>
  );
}

/* ---- category icons (square tiles) ---- */
export function IconHair(p: P) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden {...p}>
      <circle cx="19" cy="46" r="8" fill="none" stroke={C.rose} strokeWidth="5" />
      <circle cx="45" cy="46" r="8" fill="none" stroke={C.rose} strokeWidth="5" />
      <path d="M23 40L44 10M41 40L20 10" stroke={C.ink} strokeWidth="6" strokeLinecap="round" />
      <circle cx="32" cy="27" r="3.2" fill={C.amber} />
    </svg>
  );
}
export function IconSkin(p: P) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden {...p}>
      <ellipse cx="32" cy="34" rx="18" ry="22" fill={C.peach} />
      <path d="M14 30c4-14 32-14 36 0-6-6-30-6-36 0z" fill={C.ink} />
      <circle cx="25" cy="36" r="2.6" fill={C.ink} />
      <circle cx="39" cy="36" r="2.6" fill={C.ink} />
      <path d="M26 46c3 3 9 3 12 0" stroke={C.ink} strokeWidth="3" fill="none" strokeLinecap="round" />
      <path d="M50 12l1.8 5 5 1.8-5 1.8-1.8 5-1.8-5-5-1.8 5-1.8z" fill={C.amber} />
    </svg>
  );
}
export function IconNails(p: P) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden {...p}>
      <rect x="22" y="30" width="20" height="28" rx="6" fill={C.peach} />
      <path d="M22 30c0-14 20-14 20 0z" fill={C.rose} />
      <rect x="26" y="34" width="4" height="12" rx="2" fill={C.white} opacity="0.6" />
      <path d="M52 10l1.6 4.4 4.4 1.6-4.4 1.6L52 22l-1.6-4.4L46 16l4.4-1.6z" fill={C.amber} />
    </svg>
  );
}
export function IconSpa(p: P) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden {...p}>
      <ellipse cx="32" cy="50" rx="22" ry="7" fill={C.ink} />
      <ellipse cx="32" cy="42" rx="14" ry="5" fill={C.stone} />
      <ellipse cx="32" cy="33" rx="10" ry="4" fill={C.peach} />
      <path d="M32 6c8 8 8 16 0 22-8-6-8-14 0-22z" fill={C.teal} />
    </svg>
  );
}
export const CATEGORY_ART = {
  hair: { Icon: IconHair, bg: C.rose100 },
  skin: { Icon: IconSkin, bg: C.amber100 },
  nails: { Icon: IconNails, bg: C.plum100 },
  spa: { Icon: IconSpa, bg: C.teal100 },
} as const;
export type Category = keyof typeof CATEGORY_ART;

/** Tile = icon on a soft coloured rounded square. */
export function CategoryTile({ category, size = 56 }: { category: string; size?: number }) {
  const a = CATEGORY_ART[category as Category] ?? CATEGORY_ART.hair;
  return (
    <span className="inline-flex shrink-0 items-center justify-center rounded-2xl" style={{ width: size, height: size, background: a.bg }}>
      <a.Icon width={size * 0.64} height={size * 0.64} />
    </span>
  );
}

/* ---- stylist avatars: same face, different hair / skin / top ---- */
export function Avatar({ hair, skin, top, long = false, ...p }: { hair: string; skin: string; top: string; long?: boolean } & P) {
  return (
    <svg viewBox="0 0 120 120" aria-hidden {...p}>
      <circle cx="60" cy="60" r="60" fill={C.rose100} />
      {long && <path d="M26 62c-4-34 16-48 34-48s38 14 34 48l-4 34H30z" fill={hair} />}
      <path d="M20 120c2-26 20-38 40-38s38 12 40 38z" fill={top} />
      <rect x="52" y="70" width="16" height="16" rx="6" fill={skin} />
      <ellipse cx="60" cy="52" rx="22" ry="25" fill={skin} />
      <path d={long ? "M36 50c0-22 12-30 24-30s26 8 24 30c-8-10-14-14-24-14S44 40 36 50z" : "M37 48c-2-20 10-30 24-30s24 8 22 30c-6-8-10-12-22-12s-18 4-24 12z"} fill={hair} />
      <circle cx="51" cy="54" r="2.8" fill={C.ink} />
      <circle cx="69" cy="54" r="2.8" fill={C.ink} />
      <path d="M52 66c4 4 12 4 16 0" stroke={C.ink} strokeWidth="3" fill="none" strokeLinecap="round" />
    </svg>
  );
}
export const STYLISTS = [
  { name: "Neha", title: "Senior Stylist", line: "Cuts, colour, hair spa and bridal looks", art: { hair: "#6b4a3a", skin: "#f5c9a6", top: C.rose, long: true } },
  { name: "Rohit", title: "Stylist", line: "Men's cuts, colour and keratin", art: { hair: "#5b3a29", skin: "#e0a67c", top: C.teal } },
  { name: "Sana", title: "Skin & Nail Specialist", line: "Facials, manicures and nail art", art: { hair: "#7c2d12", skin: "#f1bf98", top: C.plum, long: true } },
  { name: "Meera", title: "Spa Therapist", line: "Massages and relaxing facials", art: { hair: "#4a2f24", skin: "#d9966b", top: C.amber, long: true } },
] as const;

/* ---- how-it-works step icons ---- */
export function StepCalendar(p: P) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden {...p}>
      <rect x="8" y="14" width="48" height="42" rx="9" fill={C.white} stroke={C.ink} strokeWidth="4" />
      <rect x="8" y="14" width="48" height="14" rx="7" fill={C.rose} />
      <rect x="20" y="6" width="6" height="14" rx="3" fill={C.ink} />
      <rect x="38" y="6" width="6" height="14" rx="3" fill={C.ink} />
      <circle cx="22" cy="40" r="4" fill={C.stone} /><circle cx="32" cy="40" r="4" fill={C.stone} /><circle cx="42" cy="40" r="5" fill={C.amber} />
    </svg>
  );
}
export function StepPay(p: P) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden {...p}>
      <rect x="14" y="4" width="36" height="56" rx="9" fill={C.ink} />
      <rect x="19" y="12" width="26" height="38" rx="4" fill={C.white} />
      <circle cx="32" cy="27" r="9" fill={C.amber} />
      <text x="32" y="32" textAnchor="middle" fontSize="13" fontWeight="700" fill={C.ink}>₹</text>
      <rect x="23" y="41" width="18" height="4" rx="2" fill={C.teal} />
    </svg>
  );
}
export function StepChat(p: P) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden {...p}>
      <path d="M8 12h40a6 6 0 016 6v22a6 6 0 01-6 6H28l-12 10v-10H8a6 6 0 01-6-6V18a6 6 0 016-6z" fill={C.teal} transform="translate(4 0)" />
      <path d="M22 30l7 7 14-15" stroke={C.white} strokeWidth="5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
export function Pin(p: P) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden {...p}>
      <path d="M32 6c-12 0-20 9-20 20 0 15 20 32 20 32s20-17 20-32c0-11-8-20-20-20z" fill={C.rose} />
      <circle cx="32" cy="26" r="8" fill={C.white} />
    </svg>
  );
}
