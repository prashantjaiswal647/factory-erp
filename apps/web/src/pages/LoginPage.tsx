import { LockKeyhole, LogIn } from "lucide-react";
import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (user) {
    return <Navigate to={user.role === "Operator" ? "/production" : "/"} replace />;
  }

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const nextUser = await login(username, password);
      const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      navigate(from && from !== "/login" ? from : nextUser.role === "Operator" ? "/production" : "/", {
        replace: true
      });
    } catch {
      setError("Invalid username or password.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-zinc-100 px-4 text-zinc-950">
      <section className="w-full max-w-md rounded-md border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-md bg-brand-600 text-white">
            <LockKeyhole className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">AI ERP Login</h1>
            <p className="text-sm text-zinc-500">Secure factory operations access</p>
          </div>
        </div>

        <form className="mt-6 space-y-4" onSubmit={submitLogin}>
          <div>
            <label className="text-sm font-medium text-zinc-700" htmlFor="username">
              Username
            </label>
            <input
              className="mt-1 h-11 w-full rounded-md border border-zinc-200 bg-zinc-50 px-3 text-sm outline-none transition focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
              id="username"
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
              type="text"
              value={username}
            />
          </div>

          <div>
            <label className="text-sm font-medium text-zinc-700" htmlFor="password">
              Password
            </label>
            <input
              className="mt-1 h-11 w-full rounded-md border border-zinc-200 bg-zinc-50 px-3 text-sm outline-none transition focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
              id="password"
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              type="password"
              value={password}
            />
          </div>

          {error ? <p className="rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</p> : null}

          <button
            className="flex h-11 w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
            disabled={isSubmitting}
            type="submit"
          >
            <LogIn className="h-4 w-4" />
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
