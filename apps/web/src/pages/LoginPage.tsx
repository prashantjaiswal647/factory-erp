import { Bot, Check, LockKeyhole, LogIn, UserPlus } from "lucide-react";
import axios from "axios";
import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { roleHomePath } from "../components/PrivateRoute";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";

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

type AuthTab = "login" | "signup";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<AuthTab>("login");
  const [identifier, setIdentifier] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [signupForm, setSignupForm] = useState({
    full_name: "",
    email: "",
    phone_number: "",
    factory_name: "",
    password: "",
    confirm_password: ""
  });
  const [signupCountryCode, setSignupCountryCode] = useState("+91");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (user) {
    return <Navigate to={roleHomePath(user.role)} replace />;
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const nextUser = await login(identifier.trim(), loginPassword);
      localStorage.setItem("factory_id", String(nextUser.factory_id ?? ""));
      navigate("/dashboard", { replace: true });
    } catch (caught) {
      setError(getErrorMessage(caught, "Invalid phone number/email or password."));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitSignup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);

    if (signupForm.password !== signupForm.confirm_password) {
      setError("Password and Confirm Password do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await api.post("/api/auth/signup", {
        full_name: signupForm.full_name.trim(),
        email: signupForm.email.trim() || null,
        phone_number: `${signupCountryCode}${signupForm.phone_number.trim()}`,
        factory_name: signupForm.factory_name.trim(),
        password: signupForm.password
      });
      setSignupForm({
        full_name: "",
        email: "",
        phone_number: "",
        factory_name: "",
        password: "",
        confirm_password: ""
      });
      setNotice("Sign up successful. Please log in with your email or phone number.");
      setActiveTab("login");
    } catch (caught) {
      setError(getErrorMessage(caught, "Sign up failed."));
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
        existing.addEventListener("error", () => reject(new Error("Google sign-up failed to load")), { once: true });
        return;
      }
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Google sign-up failed to load"));
      document.body.appendChild(script);
    });
  }

  async function startGoogleSignup() {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!clientId) {
      setError("VITE_GOOGLE_CLIENT_ID is not configured.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await loadGoogleScript();
      window.google?.accounts.id.initialize({
        client_id: clientId,
        callback: async (response) => {
          if (!response.credential) {
            setError("Google sign up cancelled.");
            setIsSubmitting(false);
            return;
          }
          try {
            await api.post("/api/auth/google", { credential: response.credential });
            setNotice("Google sign up successful. Please log in.");
            setActiveTab("login");
          } catch {
            setError("Google sign up failed.");
          } finally {
            setIsSubmitting(false);
          }
        }
      });
      window.google?.accounts.id.prompt();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Google sign up failed.");
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#07100f] px-4 py-10 text-white">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_25%_20%,rgba(178,255,89,0.14),transparent_28%),radial-gradient(circle_at_75%_10%,rgba(0,77,64,0.55),transparent_35%),linear-gradient(135deg,#07100f_0%,#111827_60%,#001f1b_100%)]" />
      <section className="relative z-10 w-full max-w-md">
        <Link className="mb-8 inline-flex items-center gap-3 text-sm font-semibold text-zinc-300 hover:text-[#B2FF59]" to="/">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-[#004D40] text-[#B2FF59]">
            <Bot className="h-5 w-5" />
          </span>
          Munshi AI
        </Link>

        <div className="rounded-lg border border-[#B2FF59]/20 bg-zinc-950/85 p-6 shadow-[0_0_60px_rgba(0,77,64,.35)] backdrop-blur">
          <div className="mb-6 grid grid-cols-2 rounded-md border border-white/10 bg-white/5 p-1">
            <TabButton active={activeTab === "login"} label="Login" onClick={() => switchTab("login")} />
            <TabButton active={activeTab === "signup"} label="Sign Up" onClick={() => switchTab("signup")} />
          </div>

          <div className="mb-6 flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-md bg-[#004D40] text-[#B2FF59] shadow-[0_0_24px_rgba(178,255,89,.2)]">
              {activeTab === "login" ? <LockKeyhole className="h-5 w-5" /> : <UserPlus className="h-5 w-5" />}
            </div>
            <div>
              <h1 className="text-xl font-semibold">{activeTab === "login" ? "Secure Login" : "Create Owner Account"}</h1>
              <p className="text-sm text-zinc-400">{activeTab === "login" ? "Use email or phone number" : "Start a new factory workspace"}</p>
            </div>
          </div>

          {activeTab === "login" ? (
            <form onSubmit={submitLogin}>
              <div className="space-y-4">
                <Field label="Email or Phone Number" value={identifier} onChange={setIdentifier} autoComplete="username" />
                <Field label="Password" value={loginPassword} onChange={setLoginPassword} autoComplete="current-password" type="password" />
              </div>
              <Messages error={error} notice={notice} />
              <button className="mt-6 flex h-11 w-full items-center justify-center gap-2 rounded-md bg-[#B2FF59] px-4 text-sm font-bold text-[#07100f] shadow-[0_0_28px_rgba(178,255,89,.35)] hover:bg-white disabled:cursor-not-allowed disabled:bg-zinc-500" disabled={isSubmitting} type="submit">
                <LogIn className="h-4 w-4" />
                {isSubmitting ? "Signing in..." : "Login"}
              </button>
            </form>
          ) : (
            <form onSubmit={submitSignup}>
              <div className="space-y-4">
                <Field label="Full Name" value={signupForm.full_name} onChange={(full_name) => setSignupForm({ ...signupForm, full_name })} autoComplete="name" />
                <Field label="Email (Optional)" value={signupForm.email} onChange={(email) => setSignupForm({ ...signupForm, email })} autoComplete="email" required={false} type="email" />
                <PhoneField
                  countryCode={signupCountryCode}
                  phoneNumber={signupForm.phone_number}
                  onCountryCodeChange={setSignupCountryCode}
                  onPhoneNumberChange={(phone_number) => setSignupForm({ ...signupForm, phone_number })}
                />
                <Field label="Factory Name" value={signupForm.factory_name} onChange={(factory_name) => setSignupForm({ ...signupForm, factory_name })} />
                <Field label="Password" value={signupForm.password} onChange={(password) => setSignupForm({ ...signupForm, password })} autoComplete="new-password" type="password" />
                <Field label="Confirm Password" value={signupForm.confirm_password} onChange={(confirm_password) => setSignupForm({ ...signupForm, confirm_password })} autoComplete="new-password" type="password" />
              </div>
              <Messages error={error} notice={notice} />
              <button className="mt-6 flex h-11 w-full items-center justify-center gap-2 rounded-md bg-[#B2FF59] px-4 text-sm font-bold text-[#07100f] shadow-[0_0_28px_rgba(178,255,89,.35)] hover:bg-white disabled:cursor-not-allowed disabled:bg-zinc-500" disabled={isSubmitting} type="submit">
                <Check className="h-4 w-4" />
                {isSubmitting ? "Creating..." : "Sign Up"}
              </button>
              <button className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-md border border-white/15 bg-white px-4 text-sm font-bold text-zinc-950 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:bg-zinc-500" disabled={isSubmitting} onClick={startGoogleSignup} type="button">
                <span className="text-lg font-bold text-[#4285F4]">G</span>
                Sign up with Google
              </button>
            </form>
          )}
        </div>
      </section>
    </main>
  );

  function switchTab(tab: AuthTab) {
    setActiveTab(tab);
    setError(null);
    setNotice(null);
  }
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className={`h-10 rounded-md text-sm font-semibold transition ${active ? "bg-[#B2FF59] text-[#07100f]" : "text-zinc-300 hover:bg-white/10 hover:text-white"}`} type="button" onClick={onClick}>
      {label}
    </button>
  );
}

function Messages({ error, notice }: { error: string | null; notice: string | null }) {
  return (
    <>
      {error ? <p className="mt-4 rounded-md border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200">{error}</p> : null}
      {notice ? <p className="mt-4 rounded-md border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-200">{notice}</p> : null}
    </>
  );
}

function getErrorMessage(caught: unknown, fallback: string) {
  if (!axios.isAxiosError(caught)) return fallback;
  const detail = caught.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item?.msg === "string") return item.msg;
        if (typeof item === "string") return item;
        return "";
      })
      .filter(Boolean)
      .join(" ");
  }
  return caught.message || fallback;
}

function Field({ label, value, onChange, type = "text", autoComplete, required = true }: { label: string; value: string; onChange: (value: string) => void; type?: string; autoComplete?: string; required?: boolean }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-200">{label}</span>
      <input
        autoComplete={autoComplete}
        className="mt-1 h-11 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-white outline-none transition placeholder:text-zinc-500 focus:border-[#B2FF59]/70 focus:ring-2 focus:ring-[#B2FF59]/15"
        onChange={(event) => onChange(event.target.value)}
        required={required}
        type={type}
        value={value}
      />
    </label>
  );
}

function PhoneField({
  countryCode,
  onCountryCodeChange,
  onPhoneNumberChange,
  phoneNumber
}: {
  countryCode: string;
  onCountryCodeChange: (value: string) => void;
  onPhoneNumberChange: (value: string) => void;
  phoneNumber: string;
}) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-zinc-200">Phone Number</span>
      <div className="mt-1 flex h-11 overflow-hidden rounded-md border border-white/10 bg-white/5 focus-within:border-[#B2FF59]/70 focus-within:ring-2 focus-within:ring-[#B2FF59]/15">
        <select
          className="w-24 border-r border-white/10 bg-white/10 px-3 text-sm font-semibold text-white outline-none"
          value={countryCode}
          onChange={(event) => onCountryCodeChange(event.target.value)}
        >
          <option className="text-zinc-950" value="+91">+91</option>
          <option className="text-zinc-950" value="+1">+1</option>
          <option className="text-zinc-950" value="+44">+44</option>
          <option className="text-zinc-950" value="+971">+971</option>
        </select>
        <input
          autoComplete="tel-national"
          className="min-w-0 flex-1 bg-transparent px-3 text-sm text-white outline-none placeholder:text-zinc-500"
          inputMode="tel"
          required
          type="tel"
          value={phoneNumber}
          onChange={(event) => onPhoneNumberChange(event.target.value)}
        />
      </div>
    </label>
  );
}
