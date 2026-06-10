import { isOwnerLevelRole, useAuth } from "../context/AuthContext";
import TelegramConnectCard from "../components/TelegramConnectCard";

export default function Integrations() {
  const { user } = useAuth();

  if (!isOwnerLevelRole(user?.role)) {
    return (
      <div className="mx-auto w-full max-w-4xl">
        <section className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold text-zinc-950">Telegram Integration</h1>
          <p className="mt-2 text-sm text-zinc-600">
            Telegram integration is not available for your role.
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 overflow-x-hidden" data-test-id="telegram-integration-status">
      <header>
        <h1 className="text-2xl font-semibold text-zinc-950">Integrations</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Factory alerts aur daily briefing channels manage karein.
        </p>
      </header>

      <TelegramConnectCard />
    </div>
  );
}
