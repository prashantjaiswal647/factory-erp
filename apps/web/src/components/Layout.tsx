import { AlertTriangle, Bot, Boxes, Calculator, CalendarDays, ChevronDown, ClipboardList, CreditCard, Factory, FileText, Gauge, LockKeyhole, LogOut, Menu, PlugZap, ReceiptText, RotateCw, Search, Settings2, ShieldAlert, UserCog, UserRound, UsersRound, X } from "lucide-react";
import { useState, useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../context/AuthContext";
import { useDataRefresh } from "../context/DataRefreshContext";
import { getUserSubscription } from "../lib/api";
import type { DashboardSubscriptionStatus, UserSubscriptionResponse } from "../lib/api";

type NavigationItem = {
  label: string;
  href: string;
  icon: typeof Gauge;
  roles: UserRole[];
  section?: string;
};

const navigation: NavigationItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: Gauge, roles: ["Owner", "Sub-Owner"] },
  { label: "Manual Operations", href: "https://munshiai.co.in/operations", icon: ClipboardList, roles: ["Owner", "Sub-Owner"] },
  { label: "Daily Sequence", href: "/daily-sequence", icon: CalendarDays, roles: ["Owner", "Sub-Owner"] },
  { label: "Inventory", href: "/inventory", icon: Boxes, roles: ["Owner", "Sub-Owner", "Supervisor", "Operator"] },
  { label: "Onboarding", href: "/onboarding", icon: ClipboardList, roles: ["Owner", "Sub-Owner"] },
  { label: "Machine Setup", href: "/machine-onboarding", icon: Settings2, roles: ["Owner", "Sub-Owner"] },
  { label: "Calculator", href: "/calculator", icon: Calculator, roles: ["Owner", "Sub-Owner"] },
  { label: "Production", href: "/production", icon: Factory, roles: ["Owner", "Sub-Owner", "Supervisor", "Operator"] },
  { label: "Attendance", href: "/attendance", icon: CalendarDays, roles: ["Owner", "Sub-Owner", "Supervisor"] },
  { label: "Customers", href: "/customers", icon: UsersRound, roles: ["Owner", "Sub-Owner"], section: "Revenue & Accounts" },
  { label: "Sales", href: "/sales", icon: ReceiptText, roles: ["Owner", "Sub-Owner", "Supervisor"], section: "Revenue & Accounts" },
  { label: "Invoices", href: "/invoices", icon: FileText, roles: ["Owner", "Sub-Owner", "Supervisor"], section: "Revenue & Accounts" },
  { label: "Payment Collection", href: "/payments", icon: CreditCard, roles: ["Owner", "Sub-Owner", "Supervisor"], section: "Revenue & Accounts" },
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
  const location = useLocation();

  // Dynamic subscription tracking
  const [subData, setSubData] = useState<UserSubscriptionResponse | null>(null);
  const [layoutStatus, setLayoutStatus] = useState<DashboardSubscriptionStatus | null>(null);
  const [isSubscriptionUnavailable, setIsSubscriptionUnavailable] = useState(false);
  const [isBannerDismissed, setIsBannerDismissed] = useState(() => {
    if (typeof window !== "undefined") {
      return sessionStorage.getItem("dismiss_banner") === "true";
    }
    return false;
  });

  const { refreshVersion, triggerDataRefresh } = useDataRefresh();

  function buildLayoutStatus(data: UserSubscriptionResponse, role: UserRole): DashboardSubscriptionStatus {
    const daysLeft = Number(data.days_left ?? 0);
    const accessAllowed = data.access_allowed === true;
    const isExpired = !accessAllowed;
    let alertState: DashboardSubscriptionStatus["alert_state"] = "none";
    if (isExpired) {
      alertState = "expired";
    } else if (daysLeft > 0 && daysLeft <= 3) {
      alertState = "critical";
    } else if (daysLeft > 0 && daysLeft <= 10) {
      alertState = "warning";
    }

    return {
      access_allowed: accessAllowed,
      alert_state: alertState,
      should_warn: accessAllowed && daysLeft > 0 && daysLeft <= 10,
      is_expired: isExpired,
      days_left: daysLeft,
      plan_name: data.effective_plan || data.plan_name || "Free Trial",
      subscription_status: data.effective_status || data.subscription_status,
      payment_status: data.payment_status,
      subscription_start: null,
      subscription_end: data.effective_expires_at || data.subscription_end_date || data.plan_expires_at || data.trial_end_date || null,
      server_time: data.server_time,
      role
    };
  }

  async function refreshSubscriptionState() {
    if (!user) return;
    const data = await getUserSubscription(Date.now());
    setSubData(data);
    setLayoutStatus(buildLayoutStatus(data, user.role));
    setIsSubscriptionUnavailable(false);
  }

  useEffect(() => {
    let active = true;
    if (!user) return;
    const currentUser = user;
    async function fetchSub() {
      try {
        const data = await getUserSubscription(Date.now());
        if (active) {
          setSubData(data);
          setLayoutStatus(buildLayoutStatus(data, currentUser.role));
          setIsSubscriptionUnavailable(false);
        }
      } catch {
        if (active) {
          setLayoutStatus(null);
          setIsSubscriptionUnavailable(true);
        }
      }
    }
    fetchSub();
    return () => {
      active = false;
    };
  }, [refreshVersion, user]);

  useEffect(() => {
    if (!user) return;
    function refreshOnReturn() {
      if (document.visibilityState === "visible") {
        refreshSubscriptionState().catch((err) => console.error("Error refreshing subscription on tab return:", err));
      }
    }
    document.addEventListener("visibilitychange", refreshOnReturn);
    window.addEventListener("focus", refreshOnReturn);
    return () => {
      document.removeEventListener("visibilitychange", refreshOnReturn);
      window.removeEventListener("focus", refreshOnReturn);
    };
  }, [user]);

  // Load requested variables
  const planName = subData?.effective_plan || subData?.plan_name;
  const planExpiresAt = subData?.effective_expires_at || subData?.plan_expires_at;
  const daysLeft = subData?.days_left;
  const lastLogin = subData?.last_login;
  const subscriptionStatus = subData?.effective_status || subData?.subscription_status;
  const accessAllowed = subData?.access_allowed === true;
  const isTrial = subData?.is_trial === true;

  async function handleRefresh() {
    setSubData(null);
    if (typeof window !== "undefined") {
      sessionStorage.removeItem("dismiss_banner");
    }
    setIsBannerDismissed(false);
    triggerDataRefresh();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("munshi:refresh-data"));
    }
    try {
      await refreshSubscriptionState();
    } catch {
      setIsSubscriptionUnavailable(true);
    }
  }

  const visibleNavigation = navigation.filter((item) => user && item.roles.includes(user.role));
  const displayName = user?.full_name || user?.username || "User";
  const initials = displayName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "U";
  const isTrialActive = accessAllowed && isTrial;
  const trialEndLabel = subData?.raw_trial_end_date ? new Date(subData.raw_trial_end_date).toLocaleDateString("en-IN") : "";
  const subscriptionEndDate = planExpiresAt ? new Date(planExpiresAt) : null;
  const layoutSubscriptionEndDate = layoutStatus?.subscription_end ? new Date(layoutStatus.subscription_end) : subscriptionEndDate;
  const expiresSoon = Boolean(
    subscriptionStatus === "active" &&
      subscriptionEndDate &&
      subscriptionEndDate.getTime() - Date.now() <= 7 * 24 * 60 * 60 * 1000 &&
      subscriptionEndDate.getTime() >= Date.now()
  );

  function handleSignOut() {
    sessionStorage.removeItem("dismiss_banner");
    logout();
    setIsProfileMenuOpen(false);
    navigate("/login", { replace: true });
  }

  const isBillingRoute = location.pathname === "/billing" || location.pathname === "/plans";
  const isExpiredLock = layoutStatus?.is_expired === true || layoutStatus?.access_allowed === false;
  if (isExpiredLock && user?.role !== "Owner") {
    return <StaffSubscriptionLock onSignOut={handleSignOut} />;
  }

  if (isExpiredLock && user?.role === "Owner" && !isBillingRoute) {
    return <OwnerSubscriptionLock onRenew={() => navigate("/billing")} onSignOut={handleSignOut} />;
  }

  const navItems = visibleNavigation.map((item, index) => {
    const showSection = item.section && visibleNavigation[index - 1]?.section !== item.section;
    const isExternal = item.href.startsWith("http");
    const linkClassName = "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-[#4B5563] transition hover:bg-[#FFF7ED] hover:text-[#111827]";

    return (
      <div key={item.href} className={showSection ? "pt-3" : undefined}>
        {showSection ? (
          <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-[#4B5563]">
            {item.section}
          </p>
        ) : null}
        {isExternal ? (
          <a href={item.href} className={linkClassName} onClick={() => setIsMobileNavOpen(false)}>
            <item.icon className="h-4 w-4" aria-hidden="true" />
            {item.label}
          </a>
        ) : (
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
        )}
      </div>
    );
  });

  return (
    <div className="min-h-screen bg-[#FFF7ED] text-[#111827]">
      <aside className="fixed inset-y-0 left-0 z-20 hidden h-screen w-64 flex-col border-r border-[#E5E7EB] bg-white md:flex">
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
        <div className="fixed inset-0 z-30 md:hidden">
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

      <div className="md:pl-64">
        <header className="sticky top-0 z-10 flex flex-col gap-3 border-b border-[#E5E7EB] bg-white/95 px-4 py-3 backdrop-blur md:flex-row md:items-center md:justify-between lg:px-8">
          <div className="flex w-full items-center gap-3 md:min-w-0 md:flex-1">
            <button
              className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-[#E5E7EB] text-[#4B5563] md:hidden block"
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
            <button
              onClick={handleRefresh}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#E5E7EB] bg-white text-[#4B5563] shadow-sm transition-all duration-300 hover:border-[#6D28D9]/30 hover:bg-[#FFF7ED] hover:text-[#6D28D9] active:scale-95 focus:outline-none focus:ring-2 focus:ring-[#F3E8FF] group"
              type="button"
              title="Refresh Data"
              aria-label="Refresh Data"
            >
              <RotateCw className="h-4 w-4 transition-transform duration-500 group-hover:rotate-180" />
            </button>

            <div data-testid="subscription-status-card">
            {isSubscriptionUnavailable ? (
              <span
                className="inline-flex h-10 shrink-0 items-center justify-center rounded-full border border-amber-300 bg-amber-50 px-4 text-sm font-bold text-amber-800 shadow-sm"
                data-testid="subscription-fallback-message"
              >
                Subscription status unavailable
              </span>
            ) : isTrialActive ? (
              <button
                className="inline-flex h-10 shrink-0 items-center justify-center rounded-full border border-[#F59E0B]/40 bg-[#F59E0B]/15 px-4 text-sm font-bold text-[#111827] shadow-sm transition hover:bg-[#F59E0B]/25"
                type="button"
                onClick={() => navigate("/plans")}
              >
                Free Trial Active
              </button>
            ) : accessAllowed && planName ? (
              <span
                className="inline-flex h-10 shrink-0 items-center justify-center rounded-full border border-indigo-300/40 bg-gradient-to-r from-slate-900 to-indigo-950 px-4 text-sm font-bold text-white shadow-sm"
                title={`Current subscription plan: ${planName}`}
              >
                Plan: {formatPlanName(planName)}
              </span>
            ) : null}
            </div>

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
          {user?.role === "Owner" && layoutStatus?.should_warn && accessAllowed && daysLeft !== undefined && daysLeft <= 10 && !isBannerDismissed ? (
            <div
              className={`relative mb-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl border px-4 py-3 text-sm font-semibold shadow-md transition-all duration-300 ${
                daysLeft <= 3
                  ? "animate-pulse border-red-700 bg-red-600 text-white"
                  : "border-yellow-600 bg-yellow-500 text-black"
              }`}
            >
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>
                  Your {planName || "plan"} plan expires on {formatDate(layoutSubscriptionEndDate)}. Renew now to avoid interruption.
                </span>
              </div>
              <div className="flex items-center gap-3 self-end sm:self-auto">
                <button
                  onClick={() => navigate("/billing")}
                  className={`inline-flex items-center justify-center rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition-all duration-300 shadow-sm hover:scale-105 active:scale-95 ${
                    daysLeft <= 3
                      ? "bg-white text-red-700 hover:bg-red-50 focus:ring-white"
                      : "bg-black text-yellow-500 hover:bg-neutral-900 focus:ring-black"
                  }`}
                  type="button"
                >
                  Upgrade Plan
                </button>
                <button
                  onClick={() => {
                    sessionStorage.setItem("dismiss_banner", "true");
                    setIsBannerDismissed(true);
                  }}
                  className={`grid h-8 w-8 place-items-center rounded-full transition-colors ${
                    daysLeft <= 3
                      ? "hover:bg-red-700/50 text-white/80 hover:text-white"
                      : "hover:bg-yellow-600/50 text-black/80 hover:text-black"
                  }`}
                  type="button"
                  aria-label="Dismiss banner"
                  title="Dismiss banner"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          ) : null}
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function formatDate(value?: Date | null) {
  if (!value) return "the current expiry date";
  return value.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function formatPlanName(value: string) {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function OwnerSubscriptionLock({ onRenew, onSignOut }: { onRenew: () => void; onSignOut: () => void }) {
  return (
    <div className="grid min-h-screen place-items-center bg-[#111827] px-4 py-8 text-white">
      <div className="w-full max-w-2xl rounded-lg border border-white/10 bg-white p-8 text-[#111827] shadow-2xl">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-md bg-red-600 text-white">
          <LockKeyhole className="h-7 w-7" />
        </div>
        <div className="mt-5 text-center">
          <p className="text-sm font-bold uppercase tracking-wide text-red-600">Billing Required</p>
          <h1 className="mt-2 text-2xl font-black">Subscription expired</h1>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-[#4B5563]">
            Your subscription has expired. Please select a plan and complete payment to restore access to your manufacturing metrics dashboard.
          </p>
        </div>
        <div className="mt-7 grid gap-3 sm:grid-cols-2">
          <button
            className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-[#6D28D9] px-4 text-sm font-bold text-white hover:bg-[#4C1D95]"
            type="button"
            onClick={onRenew}
          >
            <CreditCard className="h-4 w-4" />
            Upgrade/Renew Plan
          </button>
          <button
            className="inline-flex h-12 items-center justify-center rounded-md border border-[#E5E7EB] bg-white px-4 text-sm font-bold text-[#111827] hover:bg-[#FFF7ED]"
            type="button"
            onClick={onSignOut}
          >
            Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}

function StaffSubscriptionLock({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div className="grid min-h-screen place-items-center bg-[#FFF7ED] px-4 py-8">
      <div className="w-full max-w-2xl rounded-lg border border-[#E5E7EB] bg-white p-8 text-center shadow-sm">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-md bg-[#FEE2E2] text-red-700">
          <ShieldAlert className="h-7 w-7" />
        </div>
        <h1 className="mt-5 text-2xl font-black text-[#111827]">System Access Suspended</h1>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-[#4B5563]">
          Your factory's subscription has expired. Please contact the Factory Owner to renew the Munshi AI application plan.
        </p>
        <button
          className="mt-7 inline-flex h-11 items-center justify-center rounded-md border border-[#E5E7EB] bg-white px-5 text-sm font-bold text-[#111827] hover:bg-[#FFF7ED]"
          type="button"
          onClick={onSignOut}
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}
