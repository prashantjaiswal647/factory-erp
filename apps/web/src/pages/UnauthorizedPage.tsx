import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { roleHomePath } from "../components/PrivateRoute";
import { useAuth } from "../context/AuthContext";

export default function UnauthorizedPage() {
  const { user } = useAuth();
  const homePath = user ? roleHomePath(user.role) : "/login";

  return (
    <main className="grid min-h-screen place-items-center bg-zinc-100 px-4 text-zinc-950">
      <section className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-6 text-center shadow-sm">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-md bg-red-50 text-red-600">
          <ShieldAlert className="h-6 w-6" />
        </div>
        <h1 className="mt-4 text-xl font-semibold">Not Authorized</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Aapke role ko is page ka access allowed nahi hai.
        </p>
        <Link className="mt-5 inline-flex h-10 items-center rounded-md bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700" to={homePath}>
          Go to Home
        </Link>
      </section>
    </main>
  );
}
