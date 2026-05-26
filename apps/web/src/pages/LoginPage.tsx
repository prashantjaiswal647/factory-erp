import { Bot, Check, LockKeyhole, LogIn, UserPlus } from "lucide-react";
import axios from "axios";
import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import PasswordInput from "../components/PasswordInput";
import PhoneNumberInput from "../components/PhoneNumberInput";
import { roleHomePath } from "../components/PrivateRoute";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { validateLocalPhone } from "../lib/phoneCountries";

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
  const { user, login, loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
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
  const [googleCompletion, setGoogleCompletion] = useState<{
    credential: string;
    email: string;
    full_name: string;
    countryCode: string;
    phoneNumber: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("tab") === "signup" || params.get("plan")) {
      setActiveTab("signup");
    }
  }, [location.search]);

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
    if (!signupForm.phone_number.trim()) {
      setError("Phone number is strictly required.");
      return;
    }
    if (!validateLocalPhone(signupCountryCode, signupForm.phone_number)) {
      setError("Please enter a valid mobile number for the selected country.");
      return;
    }

    setIsSubmitting(true);
    try {
      await api.post("/api/auth/signup", {
        full_name: signupForm.full_name.trim(),
        email: signupForm.email.trim(),
        country_code: signupCountryCode,
        phone_number: signupForm.phone_number.trim(),
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
    if (!googleClientId) {
      console.error("VITE_GOOGLE_CLIENT_ID is not configured. Google OAuth button is disabled.");
      setError("Google login abhi configure nahi hai. Normal sign up use karein.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await loadGoogleScript();
      window.google?.accounts.id.initialize({
        client_id: googleClientId,
        callback: async (response) => {
          if (!response.credential) {
            setError("Google sign up cancelled.");
            setIsSubmitting(false);
            return;
          }
          try {
            const googleResponse = await api.post("/api/auth/google", { credential: response.credential });
            if (googleResponse.data?.requires_phone_number) {
              setGoogleCompletion({
                credential: response.credential,
                email: googleResponse.data.email,
                full_name: googleResponse.data.full_name,
                countryCode: "+91",
                phoneNumber: ""
              });
              return;
            }
            await loginWithGoogle(response.credential);
            navigate("/dashboard", { replace: true });
          } catch (caught) {
            setError(getErrorMessage(caught, "Google sign up failed."));
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
    <main className="grid min-h-screen place-items-center bg-[#FFF7ED] px-4 py-10 text-[#111827]">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_25%_20%,rgba(109,40,217,0.16),transparent_30%),radial-gradient(circle_at_80%_10%,rgba(245,230,211,0.75),transparent_36%),linear-gradient(135deg,#FFF7ED_0%,#F5E6D3_58%,#F3E8FF_100%)]" />
      <section className="relative z-10 w-full max-w-md">
        <Link className="mb-8 inline-flex items-center gap-3 text-sm font-bold text-[#4C1D95] hover:text-[#6D28D9]" to="/">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-[#F3E8FF] text-[#6D28D9]">
            <Bot className="h-5 w-5" />
          </span>
          Munshi AI
        </Link>

        <div className="rounded-2xl border border-[#E5E7EB] bg-white p-6 shadow-2xl shadow-orange-100/70">
          <div className="mb-6 grid grid-cols-2 rounded-lg border border-[#E5E7EB] bg-[#FFF7ED] p-1">
            <TabButton active={activeTab === "login"} label="Login" onClick={() => switchTab("login")} />
            <TabButton active={activeTab === "signup"} label="Sign Up" onClick={() => switchTab("signup")} />
          </div>

          <div className="mb-6 flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-lg bg-[#F3E8FF] text-[#6D28D9]">
              {activeTab === "login" ? <LockKeyhole className="h-5 w-5" /> : <UserPlus className="h-5 w-5" />}
            </div>
            <div>
              <h1 className="text-xl font-black text-[#111827]">{activeTab === "login" ? "Secure Login" : "Create Owner Account"}</h1>
              <p className="text-sm text-[#4B5563]">{activeTab === "login" ? "Use email or phone number" : "Start a new factory workspace"}</p>
            </div>
          </div>

          {activeTab === "login" ? (
            <form onSubmit={submitLogin}>
              <div className="space-y-4">
                <Field label="Email or Mobile Number" placeholder="someone@gmail.com or 9876543210" value={identifier} onChange={setIdentifier} autoComplete="username" />
                <PasswordInput label="Password" value={loginPassword} onChange={setLoginPassword} autoComplete="current-password" data-testid="staff-password-input" />
              </div>
              <Messages error={error} notice={notice} />
              <button className="mt-6 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white shadow-lg shadow-purple-200 hover:bg-[#4C1D95] disabled:cursor-not-allowed disabled:bg-[#9CA3AF]" disabled={isSubmitting} type="submit">
                <LogIn className="h-4 w-4" />
                {isSubmitting ? "Signing in..." : "Login"}
              </button>
            </form>
          ) : (
            <form onSubmit={submitSignup}>
              <div className="space-y-4">
                <Field label="Full Name" value={signupForm.full_name} onChange={(full_name) => setSignupForm({ ...signupForm, full_name })} autoComplete="name" />
                <Field label="Email (Optional)" value={signupForm.email} onChange={(email) => setSignupForm({ ...signupForm, email })} autoComplete="email" type="email" required={false} />
                <PhoneNumberInput
                  countryCode={signupCountryCode}
                  localNumber={signupForm.phone_number}
                  onCountryCodeChange={setSignupCountryCode}
                  onLocalNumberChange={(phone_number) => setSignupForm({ ...signupForm, phone_number })}
                />
                <Field label="Factory Name" value={signupForm.factory_name} onChange={(factory_name) => setSignupForm({ ...signupForm, factory_name })} />
                <PasswordInput label="Password" value={signupForm.password} onChange={(password) => setSignupForm({ ...signupForm, password })} autoComplete="new-password" data-testid="signup-password-input" />
                <PasswordInput label="Confirm Password" value={signupForm.confirm_password} onChange={(confirm_password) => setSignupForm({ ...signupForm, confirm_password })} autoComplete="new-password" data-testid="signup-confirm-password-input" />
              </div>
              <Messages error={error} notice={notice} />
              <button className="mt-6 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white shadow-lg shadow-purple-200 hover:bg-[#4C1D95] disabled:cursor-not-allowed disabled:bg-[#9CA3AF]" disabled={isSubmitting} type="submit">
                <Check className="h-4 w-4" />
                {isSubmitting ? "Creating..." : "Sign Up"}
              </button>
            </form>
          )}
        </div>
      </section>
      {googleCompletion ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 px-4">
          <form className="w-full max-w-md rounded-2xl border border-[#E5E7EB] bg-white p-6 shadow-2xl shadow-purple-200/70" onSubmit={completeGoogleSignup}>
            <div className="mb-5">
              <h2 className="text-xl font-black text-[#111827]">Verify Phone Number</h2>
              <p className="mt-2 text-sm leading-6 text-[#4B5563]">
                Munshi AI uses phone numbers as the global owner identity. Add your phone number to finish Google sign up for {googleCompletion.email}.
              </p>
            </div>
            <PhoneNumberInput
              countryCode={googleCompletion.countryCode}
              localNumber={googleCompletion.phoneNumber}
              onCountryCodeChange={(countryCode) => setGoogleCompletion({ ...googleCompletion, countryCode })}
              onLocalNumberChange={(phoneNumber) => setGoogleCompletion({ ...googleCompletion, phoneNumber })}
            />
            <Messages error={error} notice={notice} />
            <div className="mt-6 flex gap-3">
              <button className="h-11 flex-1 rounded-lg border border-[#E5E7EB] px-4 text-sm font-semibold text-[#111827] hover:bg-[#FFF7ED]" type="button" onClick={() => setGoogleCompletion(null)}>
                Cancel
              </button>
              <button className="h-11 flex-1 rounded-lg bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95] disabled:cursor-not-allowed disabled:bg-[#9CA3AF]" disabled={isSubmitting} type="submit">
                {isSubmitting ? "Creating..." : "Complete Sign Up"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </main>
  );

  function switchTab(tab: AuthTab) {
    setActiveTab(tab);
    setError(null);
    setNotice(null);
  }

  async function completeGoogleSignup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!googleCompletion) return;
    setIsSubmitting(true);
    setError(null);
    setNotice(null);
    if (!validateLocalPhone(googleCompletion.countryCode, googleCompletion.phoneNumber)) {
      setError("Please enter a valid mobile number for the selected country.");
      setIsSubmitting(false);
      return;
    }
    try {
      await api.post("/api/auth/google/complete", {
        credential: googleCompletion.credential,
        country_code: googleCompletion.countryCode,
        phone_number: googleCompletion.phoneNumber.trim()
      });
      await loginWithGoogle(googleCompletion.credential);
      navigate("/dashboard", { replace: true });
    } catch (caught) {
      setError(getErrorMessage(caught, "Google sign up failed."));
    } finally {
      setIsSubmitting(false);
    }
  }
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className={`h-10 rounded-md text-sm font-bold transition ${active ? "bg-[#6D28D9] text-white shadow-sm" : "text-[#4B5563] hover:bg-white hover:text-[#111827]"}`} type="button" onClick={onClick}>
      {label}
    </button>
  );
}

function Messages({ error, notice }: { error: string | null; notice: string | null }) {
  return (
    <>
      {error ? <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-[#DC2626]">{error}</p> : null}
      {notice ? <p className="mt-4 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm font-medium text-[#16A34A]">{notice}</p> : null}
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

function Field({ label, value, onChange, type = "text", autoComplete, placeholder, required = true }: { label: string; value: string; onChange: (value: string) => void; type?: string; autoComplete?: string; placeholder?: string; required?: boolean }) {
  return (
    <label className="block text-sm">
      <span className="font-semibold text-[#111827]">{label}</span>
      <input
        autoComplete={autoComplete}
        className="mt-1 h-11 w-full rounded-lg border border-[#E5E7EB] bg-white px-3 text-sm text-[#111827] outline-none transition placeholder:text-[#9CA3AF] focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF]"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        required={required}
        type={type}
        value={value}
      />
    </label>
  );
}
