import { Bot, Crown, HardHat, LockKeyhole, LogIn, Wrench } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { roleHomePath } from "../components/PrivateRoute";
import { useAuth } from "../context/AuthContext";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (response: { credential?: string }) => void }) => void;
          prompt: () => void;
        };
      };
    };
  }
}

const roleCards = [
  { icon: Crown, label: "Owner", text: "Full dashboard, hisaab aur control." },
  { icon: HardHat, label: "Supervisor", text: "Production, sales aur collection." },
  { icon: Wrench, label: "Operator", text: "Inventory aur production entry." }
];

export default function LoginPage() {
  const { user, login, loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [factoryId, setFactoryId] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (user) {
    return <Navigate to={roleHomePath(user.role)} replace />;
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const nextUser = await login(username, password, factoryId ? Number(factoryId) : undefined);
      const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      navigate(from && from !== "/login" ? from : roleHomePath(nextUser.role), {
        replace: true
      });
    } catch {
      setError("Invalid factory, username, phone, or password.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function loadGoogleScript() {
    if (window.google?.accounts?.id) return;
    await new Promise<void>((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>('script[src="https://accounts.google.com/gsi/client"]');
      if (existing) {
        existing.addEventListener("load", () => resolve(), { once: true });
        existing.addEventListener("error", () => reject(new Error("Google sign-in failed to load")), { once: true });
        return;
      }
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Google sign-in failed to load"));
      document.body.appendChild(script);
    });
  }

  async function startGoogleLogin() {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) {
      setError("VITE_GOOGLE_CLIENT_ID is not configured.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await loadGoogleScript();
      window.google?.accounts.id.initialize({
        client_id: clientId,
        callback: async (response) => {
          if (!response.credential) {
            setError("Google login cancelled.");
            setIsSubmitting(false);
            return;
          }
          try {
            const nextUser = await loginWithGoogle(response.credential);
            navigate(roleHomePath(nextUser.role), { replace: true });
          } catch {
            setError("Google login failed.");
          } finally {
            setIsSubmitting(false);
          }
        }
      });
      window.google?.accounts.id.prompt();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Google login failed.");
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#07100f] px-4 py-10 text-white">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_25%_20%,rgba(178,255,89,0.14),transparent_28%),radial-gradient(circle_at_75%_10%,rgba(0,77,64,0.55),transparent_35%),linear-gradient(135deg,#07100f_0%,#111827_60%,#001f1b_100%)]" />
      <section className="relative z-10 w-full max-w-5xl">
        <Link className="mb-8 inline-flex items-center gap-3 text-sm font-semibold text-zinc-300 hover:text-[#B2FF59]" to="/">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-[#004D40] text-[#B2FF59]">
            <Bot className="h-5 w-5" />
          </span>
          Munshi AI
        </Link>

        <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
          <div className="rounded-lg border border-white/10 bg-white/[0.04] p-6 backdrop-blur">
            <p className="text-sm font-semibold uppercase tracking-widest text-[#B2FF59]">Role Gateway</p>
            <h1 className="mt-3 text-4xl font-semibold">Apna kaam, apna access.</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-zinc-400">
              Munshi AI har user ko sirf wahi tabs dikhata hai jo uske role ke liye zaroori hain.
            </p>

            <div className="mt-8 grid gap-4 md:grid-cols-3 lg:grid-cols-1">
              {roleCards.map((role) => (
                <article key={role.label} className="rounded-lg border border-white/10 bg-zinc-950/60 p-4">
                  <role.icon className="h-7 w-7 text-[#B2FF59]" />
                  <h2 className="mt-3 font-semibold">{role.label}</h2>
                  <p className="mt-1 text-sm text-zinc-400">{role.text}</p>
                </article>
              ))}
            </div>
          </div>

          <form className="rounded-lg border border-[#B2FF59]/20 bg-zinc-950/80 p-6 shadow-[0_0_60px_rgba(0,77,64,.35)] backdrop-blur" onSubmit={submitLogin}>
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-md bg-[#004D40] text-[#B2FF59] shadow-[0_0_24px_rgba(178,255,89,.2)]">
                <LockKeyhole className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-xl font-semibold">Secure Login</h2>
                <p className="text-sm text-zinc-400">Factory ID + credentials</p>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              <Field label="Factory ID" value={factoryId} onChange={setFactoryId} inputMode="numeric" type="number" />
              <Field label="Username / Phone" value={username} onChange={setUsername} autoComplete="username" />
              <Field label="Password" value={password} onChange={setPassword} autoComplete="current-password" type="password" />
            </div>

            {error ? <p className="mt-4 rounded-md border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200">{error}</p> : null}

            <button className="mt-6 flex h-11 w-full items-center justify-center gap-2 rounded-md bg-[#B2FF59] px-4 text-sm font-bold text-[#07100f] shadow-[0_0_28px_rgba(178,255,89,.35)] hover:bg-white disabled:cursor-not-allowed disabled:bg-zinc-500" disabled={isSubmitting} type="submit">
              <LogIn className="h-4 w-4" />
              {isSubmitting ? "Signing in..." : "Login to Munshi AI"}
            </button>
            <button
              className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-md border border-white/15 bg-white px-4 text-sm font-bold text-zinc-950 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:bg-zinc-500"
              disabled={isSubmitting}
              onClick={startGoogleLogin}
              type="button"
            >
              <span className="text-lg font-bold text-[#4285F4]">G</span>
              Sign in with Google
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}

function Field({ label, value, onChange, type = "text", inputMode, autoComplete }: { label: string; value: string; onChange: (value: string) => void; type?: string; inputMode?: "numeric"; autoComplete?: string }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-200">{label}</span>
      <input
        autoComplete={autoComplete}
        className="mt-1 h-11 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-white outline-none transition placeholder:text-zinc-500 focus:border-[#B2FF59]/70 focus:ring-2 focus:ring-[#B2FF59]/15"
        inputMode={inputMode}
        onChange={(event) => onChange(event.target.value)}
        onFocus={(event) => event.target.select()}
        required
        type={type}
        value={value}
      />
    </label>
  );
}
