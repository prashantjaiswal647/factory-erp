import {
  ArrowRight,
  BarChart3,
  Bot,
  Boxes,
  Check,
  Factory,
  FileSearch,
  Menu,
  ShieldAlert,
  UsersRound,
  X
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

const navLinks = [
  { label: "About", href: "#about" },
  { label: "Features", href: "#features" },
  { label: "Plans", href: "#plans" }
];

const botRoles = [
  {
    icon: FileSearch,
    title: "Munshi Bot data nikalega",
    text: "Production entry, sales record, stock update aur daily hisaab ko smart format mein convert karega."
  },
  {
    icon: Boxes,
    title: "Munshi Bot stock ka hisab rakhega",
    text: "Raw material, finished goods aur low-stock alerts ka real-time control aapko milega."
  },
  {
    icon: UsersRound,
    title: "Munshi Bot staff par nazar rakhega",
    text: "Shift output, attendance aur staff performance ko simple dashboard mein dikhayega."
  },
  {
    icon: ShieldAlert,
    title: "Munshi Bot nuksan se bachayega",
    text: "Wastage, pending payment, profit/loss aur risky patterns par timely alert dega."
  }
];

const plans = [
  {
    name: "Basic Plan",
    subtitle: "Chhoti factories ke liye perfect",
    machineLimit: "Up to 7 machines",
    highlight: "7-Day Free Trial included",
    features: ["Production aur stock tracking", "Basic AI Supervisor alerts", "Owner dashboard", "Simple team workflow"],
    featured: false
  },
  {
    name: "Premium Plan",
    subtitle: "Growing factories ke liye",
    machineLimit: "Unlimited machines",
    highlight: "7-Day Free Trial included",
    features: ["Advanced AI Supervisor", "Unlimited machine setup", "Profit/Loss intelligence", "Inventory forecast aur staff insights"],
    featured: true
  }
];

export default function LandingPage() {
  const [open, setOpen] = useState(false);

  return (
    <main className="min-h-screen overflow-hidden bg-[#07100f] text-white">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_25%_20%,rgba(178,255,89,0.14),transparent_28%),radial-gradient(circle_at_75%_10%,rgba(0,77,64,0.55),transparent_35%),linear-gradient(135deg,#07100f_0%,#111827_60%,#001f1b_100%)]" />

      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#07100f]/80 backdrop-blur-xl">
        <nav className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 lg:px-8">
          <Link className="flex items-center gap-2" to="/">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-[#004D40] text-[#B2FF59] shadow-[0_0_24px_rgba(178,255,89,.2)]">
              <Bot className="h-5 w-5" />
            </span>
            <span>
              <span className="block text-sm font-semibold leading-4">Munshi AI</span>
              <span className="block text-xs text-zinc-400">Factory Bot</span>
            </span>
          </Link>

          <div className="hidden items-center gap-6 text-sm font-medium text-zinc-300 md:flex">
            {navLinks.map((item) => (
              <a key={item.href} className="hover:text-[#B2FF59]" href={item.href}>
                {item.label}
              </a>
            ))}
            <Link className="hover:text-[#B2FF59]" to="/login">
              Login
            </Link>
            <Link className="rounded-md bg-[#B2FF59] px-4 py-2 font-bold text-[#07100f] shadow-[0_0_28px_rgba(178,255,89,.35)] hover:bg-white" to="/login">
              Sign Up
            </Link>
          </div>

          <button className="grid h-10 w-10 place-items-center rounded-md border border-white/10 text-zinc-200 md:hidden" type="button" onClick={() => setOpen((value) => !value)}>
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </nav>

        {open ? (
          <div className="border-t border-white/10 bg-[#07100f] px-4 py-4 md:hidden">
            <div className="grid gap-3 text-sm font-medium text-zinc-300">
              {navLinks.map((item) => (
                <a key={item.href} href={item.href} onClick={() => setOpen(false)}>
                  {item.label}
                </a>
              ))}
              <Link className="rounded-md border border-white/15 px-4 py-2 text-center font-semibold" to="/login">
                Login
              </Link>
              <Link className="rounded-md bg-[#B2FF59] px-4 py-2 text-center font-bold text-[#07100f]" to="/login">
                Sign Up
              </Link>
            </div>
          </div>
        ) : null}
      </header>

      <section id="about" className="relative z-10 mx-auto grid max-w-7xl gap-10 px-4 py-12 md:py-16 lg:grid-cols-[1fr_0.9fr] lg:px-8 lg:py-20">
        <div className="flex flex-col justify-center">
          <div className="mb-5 inline-flex w-fit items-center gap-2 rounded-full border border-[#B2FF59]/30 bg-[#B2FF59]/10 px-3 py-1 text-sm font-semibold text-[#B2FF59]">
            <Bot className="h-4 w-4" />
            Aapki factory ka intelligent bot
          </div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-white md:text-6xl">
            Aapki Factory Ka Apna AI Supervisor - Munshi AI
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-zinc-300 md:text-lg md:leading-8">
            7-Day Free Trial shuru karein aur apni production, stock, staff, aur munafa ko automate karein. Kisi complex software ki zaroorat nahi!
          </p>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <Link className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-[#B2FF59] px-5 text-sm font-bold text-[#07100f] shadow-[0_0_34px_rgba(178,255,89,.35)] hover:bg-white" to="/login">
              Start Your 7-Day Free Factory Audit
              <ArrowRight className="h-4 w-4" />
            </Link>
            <a className="inline-flex h-12 items-center justify-center rounded-md border border-white/15 px-5 text-sm font-semibold text-zinc-100 hover:border-[#B2FF59]/60 hover:text-[#B2FF59]" href="#features">
              Munshi Bot kya karega?
            </a>
          </div>
        </div>

        <MunshiIndustrialBotVisual />
      </section>

      <section id="features" className="relative z-10 mx-auto max-w-7xl px-4 py-14 lg:px-8">
        <SectionHeader
          eyebrow="Munshi Bot ka kaam"
          title="Mushkil factory kaam ab AI Bot sambhalega"
          text="Munshi AI ek intelligent bot hai jo production, stock, staff aur munafa ke important signals ko samajhkar aapko simple action batata hai."
        />
        <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {botRoles.map((role) => (
            <article key={role.title} className="rounded-lg border border-white/10 bg-white/[0.04] p-5 shadow-sm transition hover:-translate-y-1 hover:border-[#B2FF59]/50 hover:shadow-[0_0_30px_rgba(0,77,64,.25)]">
              <div className="grid h-11 w-11 place-items-center rounded-md bg-[#004D40] text-[#B2FF59]">
                <role.icon className="h-5 w-5" />
              </div>
              <h3 className="mt-5 text-lg font-semibold text-white">{role.title}</h3>
              <p className="mt-3 text-sm leading-6 text-zinc-400">{role.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="relative z-10 mx-auto grid max-w-7xl gap-8 px-4 py-14 lg:grid-cols-[0.9fr_1.1fr] lg:px-8">
        <IllustrationPlaceholder title="Responsive factory data flow / AI processing illustration" compact />
        <div className="rounded-lg border border-[#B2FF59]/20 bg-zinc-950/85 p-6 shadow-[0_0_60px_rgba(0,77,64,.35)] backdrop-blur md:p-8">
          <p className="text-sm font-semibold uppercase tracking-wide text-[#B2FF59]">Simple Workflow</p>
          <h2 className="mt-3 text-2xl font-semibold text-white md:text-3xl">Bas data daalo, Munshi Bot insight dega.</h2>
          <div className="mt-6 grid gap-4">
            {[
              ["1", "Daily production, stock, sales aur staff data enter hota hai."],
              ["2", "Munshi Bot data ko check karke galti, kami aur pattern pakadta hai."],
              ["3", "Owner ko simple alert milta hai: kya karna hai, kab karna hai."]
            ].map(([step, text]) => (
              <div key={step} className="grid grid-cols-[42px_1fr] gap-3 rounded-md border border-white/10 bg-white/[0.04] p-4">
                <span className="grid h-10 w-10 place-items-center rounded-md bg-[#004D40] text-sm font-bold text-[#B2FF59]">{step}</span>
                <p className="text-sm leading-6 text-zinc-300">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="plans" className="relative z-10 mx-auto max-w-7xl px-4 py-14 lg:px-8">
        <SectionHeader
          eyebrow="Plans"
          title="Seedha pricing, factory ke size ke hisaab se"
          text="Pehle 7-Day Free Trial use karke dekhiye. Agar Munshi Bot kaam ka lage, tab plan choose kijiye."
        />
        <div className="mt-8 grid gap-5 lg:grid-cols-2">
          {plans.map((plan) => (
            <article key={plan.name} className={`rounded-lg border p-6 shadow-[0_0_60px_rgba(0,77,64,.22)] ${plan.featured ? "border-[#B2FF59]/45 bg-[#004D40]/45" : "border-white/10 bg-zinc-950/85"}`}>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="text-2xl font-semibold text-white">{plan.name}</h3>
                  <p className="mt-1 text-sm text-zinc-400">{plan.subtitle}</p>
                </div>
                <span className="w-fit rounded-full border border-[#B2FF59]/30 bg-[#B2FF59]/10 px-3 py-1 text-xs font-bold text-[#B2FF59]">
                  {plan.highlight}
                </span>
              </div>
              <p className="mt-6 text-3xl font-semibold text-white">{plan.machineLimit}</p>
              <ul className="mt-6 grid gap-3">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex gap-3 text-sm leading-6 text-zinc-300">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-[#B2FF59]" />
                    {feature}
                  </li>
                ))}
              </ul>
              <Link className={`mt-7 inline-flex h-11 w-full items-center justify-center rounded-md text-sm font-bold ${plan.featured ? "bg-[#B2FF59] text-[#07100f] hover:bg-white" : "border border-white/15 text-zinc-100 hover:border-[#B2FF59]/60 hover:text-[#B2FF59]"}`} to="/login">
                Start 7-Day Free Trial
              </Link>
            </article>
          ))}
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-7xl px-4 py-14 lg:px-8">
        <div className="rounded-lg border border-[#B2FF59]/20 bg-zinc-950/85 p-6 text-center shadow-[0_0_60px_rgba(0,77,64,.35)] md:p-10">
          <Factory className="mx-auto h-10 w-10 text-[#B2FF59]" />
          <h2 className="mt-4 text-2xl font-semibold text-white md:text-3xl">Aaj hi factory ka free audit start karein.</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-zinc-400">
            Munshi AI aapko batayega ki production, stock, staff aur munafa mein improvement kaha ho sakta hai.
          </p>
          <Link className="mt-7 inline-flex h-12 items-center justify-center gap-2 rounded-md bg-[#B2FF59] px-6 text-sm font-bold text-[#07100f] shadow-[0_0_34px_rgba(178,255,89,.35)] hover:bg-white" to="/login">
            Start Your 7-Day Free Factory Audit
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </main>
  );
}

function SectionHeader({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return (
    <div className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-wide text-[#B2FF59]">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-normal text-white md:text-4xl">{title}</h2>
      <p className="mt-4 text-base leading-7 text-zinc-400">{text}</p>
    </div>
  );
}

function MunshiIndustrialBotVisual() {
  const signals = [
    ["Production", "94%", "Stable"],
    ["Stock Risk", "8 days", "Watch"],
    ["Wastage", "2.1%", "Low"],
    ["Munafa", "+11%", "Good"]
  ];

  return (
    <div className="relative min-h-[380px] md:min-h-[480px]">
      <div className="absolute inset-0 rounded-3xl bg-[#004D40]/35 blur-3xl" />
      <div className="relative h-full overflow-hidden rounded-2xl border border-[#B2FF59]/20 bg-zinc-950/90 p-4 shadow-[0_0_70px_rgba(0,77,64,.45)] backdrop-blur">
        <div className="absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(178,255,89,.7)_1px,transparent_1px),linear-gradient(90deg,rgba(178,255,89,.7)_1px,transparent_1px)] [background-size:28px_28px]" />
        <div className="relative grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-xl border border-white/10 bg-white/[0.04] p-4">
            <div className="mx-auto grid h-48 w-48 place-items-center rounded-full border border-[#B2FF59]/20 bg-[#004D40]/30 shadow-[0_0_44px_rgba(178,255,89,.16)] md:h-60 md:w-60">
              <div className="relative h-36 w-36 md:h-44 md:w-44">
                <div className="absolute left-1/2 top-0 h-14 w-28 -translate-x-1/2 rounded-t-3xl rounded-b-lg border border-[#B2FF59]/40 bg-zinc-900 shadow-[0_0_28px_rgba(178,255,89,.2)]">
                  <div className="absolute left-4 top-5 h-3 w-3 rounded-full bg-[#B2FF59] shadow-[0_0_16px_rgba(178,255,89,.9)]" />
                  <div className="absolute right-4 top-5 h-3 w-3 rounded-full bg-[#B2FF59] shadow-[0_0_16px_rgba(178,255,89,.9)]" />
                </div>
                <div className="absolute left-1/2 top-16 h-24 w-32 -translate-x-1/2 rounded-2xl border border-white/10 bg-gradient-to-br from-zinc-800 to-[#004D40]">
                  <div className="absolute left-1/2 top-5 grid h-12 w-20 -translate-x-1/2 place-items-center rounded-md border border-[#B2FF59]/30 bg-black/35 text-center text-[10px] font-bold leading-3 text-[#B2FF59]">
                    MUNSHI
                    <br />
                    AI BOT
                  </div>
                </div>
                <div className="absolute bottom-0 left-4 h-12 w-5 rounded-full bg-zinc-700" />
                <div className="absolute bottom-0 right-4 h-12 w-5 rounded-full bg-zinc-700" />
              </div>
            </div>
            <p className="mt-4 text-center text-sm font-semibold text-white">Industrial AI Supervisor Core</p>
            <p className="mt-1 text-center text-xs text-zinc-500">Powerful bot visual placeholder for final 3D/art asset</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.04] p-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div>
                <p className="text-sm font-semibold text-white">Factory Command Center</p>
                <p className="mt-1 text-xs text-zinc-500">Live Munshi AI signals</p>
              </div>
              <span className="rounded-full border border-[#B2FF59]/30 bg-[#B2FF59]/10 px-3 py-1 text-xs font-bold text-[#B2FF59]">Online</span>
            </div>
            <div className="mt-4 flex h-32 items-end gap-2 rounded-lg border border-white/10 bg-zinc-900 p-3">
              {[44, 68, 52, 86, 61, 92, 74, 98, 70, 88].map((height, index) => (
                <span key={`${height}-${index}`} className="flex-1 rounded-t bg-[#B2FF59]/70" style={{ height: `${height}%` }} />
              ))}
            </div>
            <div className="mt-4 overflow-hidden rounded-lg border border-white/10">
              {signals.map(([label, value, state]) => (
                <div key={label} className="grid grid-cols-3 border-b border-white/10 px-3 py-2 text-sm last:border-b-0">
                  <span className="font-medium text-zinc-200">{label}</span>
                  <span className="text-zinc-400">{value}</span>
                  <span className="text-right text-[#B2FF59]">{state}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-lg border border-[#B2FF59]/20 bg-[#B2FF59]/10 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#B2FF59]">AI Action</p>
              <p className="mt-2 text-sm leading-6 text-zinc-200">Agle 8 din mein raw material reorder karna zaroori hai.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function IllustrationPlaceholder({ title, compact = false }: { title: string; compact?: boolean }) {
  return (
    <div className={`rounded-2xl border border-[#B2FF59]/20 bg-zinc-950/85 p-4 shadow-[0_0_60px_rgba(0,77,64,.35)] backdrop-blur ${compact ? "min-h-[280px]" : "min-h-[360px] md:min-h-[460px]"}`}>
      <div className="grid h-full min-h-inherit place-items-center rounded-xl border border-dashed border-[#B2FF59]/30 bg-white/[0.04] p-6 text-center">
        <div>
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-[#004D40] text-[#B2FF59]">
            <Bot className="h-8 w-8" />
          </div>
          <p className="mt-5 text-sm font-semibold text-white">{title}</p>
          <p className="mt-2 text-xs leading-5 text-zinc-500">Illustration / image placeholder</p>
          <div className="mt-6 grid grid-cols-3 gap-2">
            {[38, 64, 48, 82, 58, 74].map((height, index) => (
              <span key={`${height}-${index}`} className="rounded bg-[#B2FF59]/50" style={{ height: `${height}px` }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
