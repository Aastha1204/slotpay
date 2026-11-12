"use client";
// 3D hero: a low-poly salon corner (mirror, chair, plant, floating scissors, sparkles) with a toon material,
// so it reads as the same flat brand style but with real depth, lighting and parallax.
// Loaded lazily (see Hero3D.tsx); nothing here runs on the booking or admin routes.
import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

const COL = {
  brand: "#0284c7", brandDark: "#0369a1", brand100: "#e0f2fe", brand200: "#bae6fd", ink: "#5b9fd0", amber: "#fcd34d",
  teal: "#2f9e8f", teal2: "#5fc4b4", peach: "#fdba74", white: "#ffffff", stone: "#cbd5e1", pink: "#ec6ea8",
};

// 3-step bright ramp: the default 2-tone toon ramp is too dark for our pastel palette.
let ramp: THREE.DataTexture | null = null;
function getRamp() {
  if (!ramp) {
    ramp = new THREE.DataTexture(new Uint8Array([125, 195, 255]), 3, 1, THREE.RedFormat);
    ramp.minFilter = ramp.magFilter = THREE.NearestFilter;
    ramp.needsUpdate = true;
  }
  return ramp;
}
const Toon = ({ color }: { color: string }) => <meshToonMaterial color={color} gradientMap={getRamp()} />;
const lerp = THREE.MathUtils.lerp;

function Mirror() {
  return (
    <group position={[-1.55, 0.15, -0.5]} rotation={[0, 0.38, 0]}>
      <mesh scale={[1, 1.3, 1]}><torusGeometry args={[1, 0.12, 16, 56]} /><Toon color={COL.ink} /></mesh>
      <mesh scale={[1, 1.3, 1]} position={[0, 0, -0.02]}><circleGeometry args={[1, 56]} /><Toon color={COL.white} /></mesh>
      <mesh position={[-0.35, 0.45, 0.0]} rotation={[0, 0, 0.55]}><planeGeometry args={[0.14, 1.5]} /><Toon color={COL.brand100} /></mesh>
      <mesh position={[-0.05, 0.28, 0.0]} rotation={[0, 0, 0.55]}><planeGeometry args={[0.07, 1.0]} /><Toon color={COL.brand100} /></mesh>
      <mesh position={[0, -1.52, 0]}><cylinderGeometry args={[0.09, 0.09, 0.5, 12]} /><Toon color={COL.ink} /></mesh>
      <mesh position={[0, -1.78, 0]}><cylinderGeometry args={[0.55, 0.62, 0.1, 28]} /><Toon color={COL.ink} /></mesh>
    </group>
  );
}

function Chair() {
  return (
    <group position={[1.55, -0.2, 0.7]} rotation={[0, -0.7, 0]}>
      <mesh position={[0, -1.52, 0]}><cylinderGeometry args={[0.62, 0.7, 0.1, 28]} /><Toon color={COL.ink} /></mesh>
      <mesh position={[0, -1.1, 0]}><cylinderGeometry args={[0.1, 0.12, 0.8, 14]} /><Toon color={COL.ink} /></mesh>
      <mesh position={[0, -0.62, 0]} rotation={[0, 0, Math.PI / 2]} scale={[0.55, 1, 1]}><capsuleGeometry args={[0.44, 0.95, 8, 20]} /><Toon color={COL.brandDark} /></mesh>
      <mesh position={[0, 0.3, -0.5]} rotation={[-0.14, 0, 0]}><capsuleGeometry args={[0.46, 0.9, 8, 20]} /><Toon color={COL.brand} /></mesh>
      <mesh position={[-0.62, -0.28, -0.05]} rotation={[Math.PI / 2, 0, 0]}><capsuleGeometry args={[0.09, 0.7, 6, 12]} /><Toon color={COL.ink} /></mesh>
      <mesh position={[0.62, -0.28, -0.05]} rotation={[Math.PI / 2, 0, 0]}><capsuleGeometry args={[0.09, 0.7, 6, 12]} /><Toon color={COL.ink} /></mesh>
    </group>
  );
}

function Plant() {
  return (
    <group position={[-2.75, -1.55, 1.1]}>
      <mesh position={[0, 0.25, 0]}><cylinderGeometry args={[0.42, 0.3, 0.5, 20]} /><Toon color={COL.amber} /></mesh>
      <mesh position={[0, 0.52, 0]}><cylinderGeometry args={[0.46, 0.46, 0.1, 20]} /><Toon color={COL.peach} /></mesh>
      {[[-0.25, 0.2], [0.25, -0.2], [0, 0.5], [-0.1, -0.5]].map(([x, r], i) => (
        <mesh key={i} position={[x * 0.9, 1.1, 0]} rotation={[0, i, r]} scale={[0.55, 1.5, 0.35]}>
          <sphereGeometry args={[0.5, 16, 12]} /><Toon color={i % 2 ? COL.teal2 : COL.teal} />
        </mesh>
      ))}
    </group>
  );
}

function Blade({ g, flip }: { g: React.RefObject<THREE.Group | null>; flip?: boolean }) {
  return (
    <group ref={g}>
      <mesh position={[0, 0.75, 0]}><boxGeometry args={[0.16, 1.5, 0.05]} /><Toon color={COL.stone} /></mesh>
      <mesh position={[0, 1.58, 0]}><coneGeometry args={[0.09, 0.22, 4]} /><Toon color={COL.stone} /></mesh>
      <mesh position={[flip ? 0.22 : -0.22, -0.28, 0]}><torusGeometry args={[0.24, 0.07, 12, 28]} /><Toon color={COL.brand} /></mesh>
    </group>
  );
}

function Scissors() {
  const a = useRef<THREE.Group>(null);
  const b = useRef<THREE.Group>(null);
  const root = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const open = 0.16 + 0.15 * Math.sin(t * 2.2);
    if (a.current && b.current) { a.current.rotation.z = open; b.current.rotation.z = -open; }
    if (root.current) { root.current.rotation.y = Math.sin(t * 0.7) * 0.7; root.current.rotation.z = -0.3 + Math.sin(t * 0.9) * 0.08; root.current.position.y = 1.35 + Math.sin(t * 1.1) * 0.12; }
  });
  return (
    <group ref={root} position={[0.2, 1.35, 1.3]} scale={0.8}>
      <Blade g={a} />
      <Blade g={b} flip />
      <mesh position={[0, 0.2, 0.05]}><sphereGeometry args={[0.1, 12, 12]} /><Toon color={COL.amber} /></mesh>
    </group>
  );
}

function Sparkle({ p, s = 0.18, c = COL.amber, sp = 1 }: { p: [number, number, number]; s?: number; c?: string; sp?: number }) {
  const r = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime() * sp;
    if (r.current) { r.current.rotation.y = t; r.current.rotation.x = t * 0.6; r.current.position.y = p[1] + Math.sin(t * 1.4) * 0.15; }
  });
  return <mesh ref={r} position={p} scale={[s, s * 1.7, s]}><octahedronGeometry args={[1, 0]} /><Toon color={c} /></mesh>;
}

function World() {
  const g = useRef<THREE.Group>(null);
  const spark = useMemo(() => [
    { p: [-2.6, 2.3, 0.4] as [number, number, number], c: COL.amber, s: 0.2, sp: 1.2 }, { p: [2.7, 0.5, -0.4] as [number, number, number], c: COL.brand, s: 0.14, sp: 0.9 },
    { p: [0.9, 2.7, -0.6] as [number, number, number], c: COL.pink, s: 0.12, sp: 1.5 }, { p: [-0.6, -1.0, 2.0] as [number, number, number], c: COL.amber, s: 0.12, sp: 1 },
    { p: [2.9, 2.2, 0.8] as [number, number, number], c: COL.teal2, s: 0.13, sp: 1.1 },
  ], []);
  useFrame(({ pointer, clock }, dt) => {
    if (!g.current) return;
    const k = 1 - Math.pow(0.001, dt); // frame-rate independent smoothing
    g.current.rotation.y = lerp(g.current.rotation.y, pointer.x * 0.45 + Math.sin(clock.getElapsedTime() * 0.35) * 0.1, k);
    g.current.rotation.x = lerp(g.current.rotation.x, -pointer.y * 0.1, k);
  });
  return (
    <group ref={g} position={[0, 0.25, 0]}>
      <mesh position={[0, -1.72, 0]}><cylinderGeometry args={[3.5, 3.5, 0.14, 64]} /><Toon color={COL.brand200} /></mesh>
      <mesh position={[0, -1.64, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[3.5, 0.04, 8, 80]} /><Toon color={COL.white} /></mesh>
      <mesh position={[2.0, 2.0, -2.2]}><sphereGeometry args={[0.8, 32, 24]} /><Toon color={COL.amber} /></mesh>
      <Mirror /><Chair /><Plant /><Scissors />
      {spark.map((s, i) => <Sparkle key={i} {...s} />)}
    </group>
  );
}

export default function HeroScene({ active, onReady }: { active: boolean; onReady: () => void }) {
  return (
    <Canvas
      camera={{ position: [0, 2.0, 10.6], fov: 34 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      frameloop={active ? "always" : "never"}
      onCreated={({ camera }) => { camera.lookAt(0, 0.1, 0); onReady(); }}
      style={{ touchAction: "pan-y" }}
    >
      <ambientLight intensity={1.0} />
      <directionalLight position={[3.5, 5, 5]} intensity={1.5} />
      <directionalLight position={[-4, 2, -2]} intensity={0.8} color={COL.brand200} />
      <World />
    </Canvas>
  );
}
