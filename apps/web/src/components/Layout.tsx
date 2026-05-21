import { Bot, Boxes, Calculator, CalendarDays, ChevronDown, ClipboardList, CreditCard, Factory, Gauge, LogOut, Menu, PlugZap, ReceiptText, Search, Settings2, UserCog, UserRound, UsersRound, WalletCards, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../context/AuthContext";

type NavigationItem = {
  label: string;
  href: string;
  icon: typeof Gauge;
  roles: UserRole[];
  section?: string;
};

const navigation: NavigationItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: Gauge, roles: ["Owner", "Sub-Owner"] },
  { label: "Inventory", href: "/inventory", icon: Boxes, roles: ["Owner", "Sub-Owner", "Supervisor", "Operator"] },
  { label: "Onboarding", href: "/onboarding", icon: ClipboardList, roles: ["Owner", "Sub-Owner"] },
  { label: "Machine Setup", href: "/machine-onboarding", icon: Settings2, roles: ["Owner", "Sub-Owner"] },
  { label: "Calculator", href: "/calculator", icon: Calculator, roles: ["Owner", "Sub-Owner"] },
  { label: "Production", href: "/production", icon: Factory, roles: ["Owner", "Sub-Owner", "Supervisor", "Operator"] },
  { label: "Attendance", href: "/attendance", icon: CalendarDays, roles: ["Owner", "Sub-Owner", "Supervisor"] },
  { label: "Customers", href: "/customers", icon: UsersRound, roles: ["Owner", "Sub-Owner"], section: "Revenue & Accounts" },
  { label: "Sales", href: "/sales", icon: ReceiptText, roles: ["Owner", "Sub-Owner", "Supervisor"], section: "Revenue & Accounts" },
  { label: "Payment Collection", href: "/payments", icon: CreditCard, roles: ["Owner", "Sub-Owner", "Supervisor"], section: "Revenue & Accounts" },
  { label: "Outstanding", href: "/outstanding", icon: WalletCards, roles: ["Owner", "Sub-Owner"], section: "Revenue & Accounts" },
  { label: "Factory Expenses", href: "/expenses", icon: ReceiptText, roles: ["Owner", "Sub-Owner", "Supervisor", "Operator"], section: "Revenue & Accounts" },
  { label: "Staff Management", href: "/staff", icon: UserCog, roles: ["Owner"], section: "Admin" },
  { label: "Integrations", href: "/integrations", icon: PlugZap, roles: ["Owner", "Sub-Owner"], section: "Admin" },
  { label: "AI Chat", href: "/ai-supervisor", icon: Bot, roles: ["Owner", "Sub-Owner", "Supervisor", "Operator"] }
];

export default function Layout() {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  const visibleNavigation = navigation.filter((item) => user && item.roles.includes(user.role));
  const displayName = user?.full_name || user?.username || "User";
  const initials = displayName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "U";
  const isTrialActive = user?.subscription_status === "trial_active" || user?.subscription_status === "trial";
  const trialEndLabel = user?.trial_end_date ? new Date(user.trial_end_date).toLocaleDateString("en-IN") : "";
  const subscriptionEndDate = user?.subscription_end_date ? new Date(user.subscription_end_date) : null;
  const expiresSoon = Boolean(
    user?.subscription_status === "active" &&
      subscriptionEndDate &&
      subscriptionEndDate.getTime() - Date.now() <= 7 * 24 * 60 * 60 * 1000 &&
      subscriptionEndDate.getTime() >= Date.now()
  );

  function handleSignOut() {
    logout();
    setIsProfileMenuOpen(false);
    navigate("/login", { replace: true });
  }

  const navItems = visibleNavigation.map((item, index) => {
    const showSection = item.section && visibleNavigation[index - 1]?.section !== item.section;

    return (
      <div key={item.href} className={showSection ? "pt-3" : undefined}>
        {showSection ? (
          <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-[#4B5563]">
            {item.section}
          </p>
        ) : null}
        <NavLink
          to={item.href}
          end={item.href === "/"}
          onClick={() => setIsMobileNavOpen(false)}
          className={({ isActive }) =>
            [
              "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition",
              isActive
                ? "bg-[#F3E8FF] text-[#4C1D95]"
                : "text-[#4B5563] hover:bg-[#FFF7ED] hover:text-[#111827]"
            ].join(" ")
          }
        >
          <item.icon className="h-4 w-4" aria-hidden="true" />
          {item.label}
        </NavLink>
      </div>
    );
  });

  return (
    <div className="min-h-screen bg-[#FFF7ED] text-[#111827]">
      <aside className="fixed inset-y-0 left-0 z-20 hidden h-screen w-64 flex-col border-r border-[#E5E7EB] bg-white lg:flex">
        <div className="flex h-16 shrink-0 items-center gap-3 border-b border-[#E5E7EB] px-5">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-[#F3E8FF] text-sm font-bold text-[#6D28D9]">
            M
          </div>
          <div>
            <p className="text-sm font-semibold leading-5">Munshi AI</p>
            <p className="text-xs text-[#4B5563]">Factory Operations</p>
          </div>
        </div>

        <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {navItems}
        </nav>
      </aside>

      {isMobileNavOpen ? (
        <div className="fixed inset-0 z-30 lg:hidden">
          <button
            className="absolute inset-0 bg-[#111827]/30"
            type="button"
            aria-label="Close navigation"
            onClick={() => setIsMobileNavOpen(false)}
          />
          <aside className="relative flex h-full max-h-screen w-72 flex-col border-r border-[#E5E7EB] bg-white shadow-xl">
            <div className="flex h-16 shrink-0 items-center justify-between border-b border-[#E5E7EB] px-5">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-md bg-[#F3E8FF] text-sm font-bold text-[#6D28D9]">
                  M
                </div>
                <div>
                  <p className="text-sm font-semibold leading-5">Munshi AI</p>
                  <p className="text-xs text-[#4B5563]">Factory Operations</p>
                </div>
              </div>
              <button
                className="grid h-9 w-9 place-items-center rounded-md border border-[#E5E7EB] text-[#4B5563]"
                type="button"
                aria-label="Close navigation"
                title="Close navigation"
                onClick={() => setIsMobileNavOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 py-4">{navItems}</nav>
          </aside>
        </div>
      ) : null}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 flex flex-col gap-3 border-b border-[#E5E7EB] bg-white/95 px-4 py-3 backdrop-blur md:flex-row md:items-center md:justify-between lg:px-8">
          <div className="flex w-full items-center gap-3 md:min-w-0 md:flex-1">
            <button
              className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-[#E5E7EB] text-[#4B5563] lg:hidden"
              type="button"
              aria-label="Open navigation"
              title="Open navigation"
              onClick={() => setIsMobileNavOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </button>

            <div className="relative min-w-0 flex-1 md:max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#4B5563]" />
              <input
                className="h-10 w-full rounded-md border border-[#E5E7EB] bg-[#FFF7ED] pl-9 pr-3 text-sm text-[#111827] outline-none transition placeholder:text-[#4B5563] focus:border-[#6D28D9] focus:bg-white focus:ring-2 focus:ring-[#F3E8FF]"
                placeholder="Search materials, orders, suppliers"
                type="search"
              />
            </div>
          </div>

          <div className="z-20 flex w-full items-center justify-between gap-3 md:w-auto md:shrink-0 md:justify-end">
            {isTrialActive ? (
              <button
                className="inline-flex h-10 shrink-0 items-center justify-center rounded-full border border-[#F59E0B]/30 bg-[#F59E0B]/10 px-4 text-sm font-semibold text-[#111827] shadow-sm transition hover:bg-[#F59E0B]/20"
                type="button"
                onClick={() => navigate("/billing")}
              >
                Free Trial
              </button>
            ) : null}

            <div className="relative">
              <button
                className="flex h-10 items-center gap-2 rounded-full border border-[#E5E7EB] bg-white pl-1.5 pr-3 text-sm font-medium text-[#4B5563] shadow-sm transition hover:border-[#6D28D9]/30 hover:bg-[#FFF7ED]"
                type="button"
                aria-expanded={isProfileMenuOpen}
                aria-haspopup="menu"
                onClick={() => setIsProfileMenuOpen((current) => !current)}
              >
                <span className="grid h-7 w-7 place-items-center rounded-full bg-[#6D28D9] text-xs font-bold text-white">
                  {initials}
                </span>
                <span className="hidden max-w-32 truncate sm:inline">{displayName}</span>
                <ChevronDown className="h-4 w-4 text-[#4B5563]" aria-hidden="true" />
              </button>

              {isProfileMenuOpen ? (
                <div className="absolute right-0 mt-2 w-56 overflow-hidden rounded-lg border border-[#E5E7EB] bg-white py-2 shadow-lg" role="menu">
                  <div className="border-b border-[#E5E7EB] px-4 pb-2">
                    <p className="truncate text-sm font-semibold text-[#111827]">{displayName}</p>
                    <p className="text-xs text-[#4B5563]">{user?.role}</p>
                  </div>
                  <button
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm font-medium text-[#4B5563] hover:bg-[#FFF7ED]"
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setIsProfileMenuOpen(false);
                      navigate("/profile");
                    }}
                  >
                    <UserRound className="h-4 w-4 text-[#6D28D9]" />
                    My Profile
                  </button>
                  <button
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm font-medium text-[#DC2626] hover:bg-[#DC2626]/10"
                    type="button"
                    role="menuitem"
                    onClick={handleSignOut}
                  >
                    <LogOut className="h-4 w-4" />
                    Sign Out
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className="px-4 py-6 lg:px-8">
          {isTrialActive ? (
            <BillingBanner tone="trial" message={`Free trial active. Trial ends on ${trialEndLabel || "your trial end date"}.`} />
          ) : null}
          {expiresSoon ? (
            <BillingBanner tone="warning" message="Your plan expires soon. Renew to avoid interruption." />
          ) : null}
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function BillingBanner({ message, tone }: { message: string; tone: "trial" | "warning" }) {
  return (
    <div
      className={`mb-5 rounded-xl border px-4 py-3 text-sm font-semibold ${
        tone === "trial"
          ? "border-[#6D28D9]/25 bg-[#F3E8FF] text-[#4C1D95]"
          : "border-[#F59E0B]/30 bg-[#F59E0B]/10 text-[#111827]"
      }`}
    >
      {message}
    </div>
  );
}
