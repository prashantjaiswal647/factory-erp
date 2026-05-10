import { Bot, Boxes, Calculator, ClipboardList, CreditCard, Factory, Gauge, LogOut, Menu, ReceiptText, Search, UsersRound, WalletCards, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

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
  { label: "Dashboard", href: "/dashboard", icon: Gauge, roles: ["Owner"] },
  { label: "Inventory", href: "/inventory", icon: Boxes, roles: ["Owner", "Supervisor", "Operator"] },
  { label: "Onboarding", href: "/onboarding", icon: ClipboardList, roles: ["Owner"] },
  { label: "Calculator", href: "/calculator", icon: Calculator, roles: ["Owner"] },
  { label: "Production", href: "/production", icon: Factory, roles: ["Owner", "Supervisor", "Operator"] },
  { label: "Customers", href: "/customers", icon: UsersRound, roles: ["Owner"], section: "Revenue & Accounts" },
  { label: "Sales", href: "/sales", icon: ReceiptText, roles: ["Owner", "Supervisor"], section: "Revenue & Accounts" },
  { label: "Payment Collection", href: "/payments", icon: CreditCard, roles: ["Owner", "Supervisor"], section: "Revenue & Accounts" },
  { label: "Outstanding", href: "/outstanding", icon: WalletCards, roles: ["Owner"], section: "Revenue & Accounts" },
  { label: "AI Chat", href: "/ai-supervisor", icon: Bot, roles: ["Owner", "Supervisor", "Operator"] }
];

export default function Layout() {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const { logout, user } = useAuth();

  const visibleNavigation = navigation.filter((item) => user && item.roles.includes(user.role));

  const navItems = visibleNavigation.map((item, index) => {
    const showSection = item.section && visibleNavigation[index - 1]?.section !== item.section;

    return (
      <div key={item.href} className={showSection ? "pt-3" : undefined}>
        {showSection ? (
          <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
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
                ? "bg-brand-50 text-brand-700"
                : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950"
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
    <div className="min-h-screen bg-zinc-100 text-zinc-950">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 border-r border-zinc-200 bg-white lg:block">
        <div className="flex h-16 items-center gap-3 border-b border-zinc-200 px-5">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-brand-600 text-sm font-bold text-white">
            AI
          </div>
          <div>
            <p className="text-sm font-semibold leading-5">AI ERP</p>
            <p className="text-xs text-zinc-500">Factory Operations</p>
          </div>
        </div>

        <nav className="space-y-1 px-3 py-4">
          {navItems}
        </nav>
      </aside>

      {isMobileNavOpen ? (
        <div className="fixed inset-0 z-30 lg:hidden">
          <button
            className="absolute inset-0 bg-zinc-950/30"
            type="button"
            aria-label="Close navigation"
            onClick={() => setIsMobileNavOpen(false)}
          />
          <aside className="relative h-full w-72 border-r border-zinc-200 bg-white shadow-xl">
            <div className="flex h-16 items-center justify-between border-b border-zinc-200 px-5">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-md bg-brand-600 text-sm font-bold text-white">
                  AI
                </div>
                <div>
                  <p className="text-sm font-semibold leading-5">AI ERP</p>
                  <p className="text-xs text-zinc-500">Factory Operations</p>
                </div>
              </div>
              <button
                className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600"
                type="button"
                aria-label="Close navigation"
                title="Close navigation"
                onClick={() => setIsMobileNavOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav className="space-y-1 px-3 py-4">{navItems}</nav>
          </aside>
        </div>
      ) : null}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b border-zinc-200 bg-white/95 px-4 backdrop-blur lg:px-8">
          <button
            className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600 lg:hidden"
            type="button"
            aria-label="Open navigation"
            title="Open navigation"
            onClick={() => setIsMobileNavOpen(true)}
          >
            <Menu className="h-4 w-4" />
          </button>

          <div className="relative max-w-md flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              className="h-10 w-full rounded-md border border-zinc-200 bg-zinc-50 pl-9 pr-3 text-sm outline-none transition placeholder:text-zinc-400 focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-100"
              placeholder="Search materials, orders, suppliers"
              type="search"
            />
          </div>

          <div className="hidden text-right sm:block">
            <p className="text-sm font-medium">{user?.username}</p>
            <p className="text-xs text-zinc-500">{user?.role}</p>
          </div>
          <button
            className="grid h-9 w-9 place-items-center rounded-md border border-zinc-200 text-zinc-600 hover:bg-zinc-50"
            onClick={logout}
            title="Sign out"
            type="button"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </header>

        <main className="px-4 py-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
