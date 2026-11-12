"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, supabase } from "@/lib/supabase";
import { DEV_AUTH, setDevToken } from "@/lib/admin";
import { PROTOTYPE, prototypeLogin } from "@/lib/prototype";

export default function AdminLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (PROTOTYPE) prototypeLogin().then((t) => (t ? router.push("/admin") : setMsg("Prototype login is unavailable. Is the API running with PROTOTYPE_MODE=true?")));
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error || !data.session) return setMsg(error?.message ?? "Sign-in failed");
    const r = await fetch(`${API_BASE}/admin/me`, {
      headers: { Authorization: `Bearer ${data.session.access_token}` },
    });
    if (r.ok) { router.push("/admin"); return; }
    setMsg("Not a staff user");
  }

  function useDevToken() {
    const t = prompt("Paste a dev token (scripts/dev_token.py)");
    if (t) { setDevToken(t.trim()); router.push("/admin"); }
  }

  return (
    <main className="mx-auto max-w-sm p-6">
      <h1 className="mb-4 text-2xl font-semibold">Glow Studio · Admin</h1>
      <form onSubmit={submit} className="space-y-3">
        <input className="w-full rounded border p-3" type="email" placeholder="Email" value={email}
          onChange={(e) => setEmail(e.target.value)} required />
        <input className="w-full rounded border p-3" type="password" placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)} required />
        <button className="w-full rounded bg-brand-700 p-3 font-medium text-white">Sign in</button>
        {msg && <p className="text-sm">{msg}</p>}
        {DEV_AUTH && <button type="button" onClick={useDevToken} className="w-full text-sm text-stone-500 underline">Use dev token (local only)</button>}
      </form>
    </main>
  );
}
