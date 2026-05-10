import { BellRing, Bot, Crown, Factory, HardHat, Menu, ReceiptText, WalletCards, Wrench, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

const features = [
  {
    icon: ReceiptText,
    title: "Hisaab-Kitab Master",
    text: "Automatic billing, ledger update aur WhatsApp alerts ek hi flow mein."
  },
  {
    icon: Factory,
    title: "Production Expert",
    text: "Bori aur reel based entry, stock deduction, aur live factory visibility."
  },
  {
    icon: WalletCards,
    title: "Vasooli Agent",
    text: "Live outstanding, one-tap collection, aur market dues par pakki nazar."
  }
];

const roles = [
  { icon: Crown, title: "Owner", text: "Profit, dues, dashboard aur pura control." },
  { icon: HardHat, title: "Supervisor", text: "Production, sales, inventory aur payments." },
  { icon: Wrench, title: "Operator", text: "Fast production aur inventory workflow." }
];

export default function LandingPage() {
  const [open, setOpen] = useState(false);

  return (
    <main className="min-h-screen overflow-hidden bg-[#07100f] text-white">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(178,255,89,0.16),transparent_28%),radial-gradient(circle_at_80%_20%,rgba(0,77,64,0.45),transparent_30%),linear-gradient(135deg,#07100f_0%,#111827_55%,#001f1b_100%)]" />
      <div className="pointer-events-none fixed inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,.35)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.35)_1px,transparent_1px)] [background-size:42px_42px]" />

      <div className="relative z-10">
        <header className="sticky top-0 z-30 border-b border-white/10 bg-[#07100f]/80 backdrop-blur-xl">
          <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 lg:px-8">
            <Link className="flex items-center gap-3" to="/">
              <span className="grid h-10 w-10 place-items-center rounded-md border border-[#B2FF59]/40 bg-[#004D40] text-[#B2FF59] shadow-[0_0_24px_rgba(178,255,89,.2)]">
                <Bot className="h-5 w-5" />
              </span>
              <span>
                <span className="block text-sm font-semibold tracking-wide">Munshi AI</span>
                <span className="block text-xs text-zinc-400">Digital Bahi-Khata</span>
              </span>
            </Link>

            <div className="hidden items-center gap-8 text-sm font-medium text-zinc-300 md:flex">
              <a className="hover:text-[#B2FF59]" href="#features">Features</a>
              <a className="hover:text-[#B2FF59]" href="#pricing">Pricing</a>
              <a className="hover:text-[#B2FF59]" href="#about">About</a>
              <Link className="rounded-md bg-[#B2FF59] px-4 py-2 font-semibold text-[#07100f] shadow-[0_0_28px_rgba(178,255,89,.35)] hover:bg-white" to="/login">
                Try Now
              </Link>
            </div>

            <button className="grid h-10 w-10 place-items-center rounded-md border border-white/10 text-zinc-200 md:hidden" type="button" onClick={() => setOpen((value) => !value)}>
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </nav>
          {open ? (
            <div className="border-t border-white/10 bg-[#07100f] px-4 py-4 md:hidden">
              <div className="grid gap-3 text-sm font-medium text-zinc-300">
                <a href="#features" onClick={() => setOpen(false)}>Features</a>
                <a href="#pricing" onClick={() => setOpen(false)}>Pricing</a>
                <a href="#about" onClick={() => setOpen(false)}>About</a>
                <Link className="rounded-md bg-[#B2FF59] px-4 py-2 text-center font-semibold text-[#07100f]" to="/login">Try Now</Link>
              </div>
            </div>
          ) : null}
        </header>

        <section className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-7xl items-center gap-10 px-4 py-14 lg:grid-cols-[1fr_0.9fr] lg:px-8">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#B2FF59]/30 bg-[#B2FF59]/10 px-3 py-1 text-sm font-medium text-[#B2FF59]">
              <BellRing className="h-4 w-4" />
              Ab dukan ka har ek paisa rahega aapki mutthi mein
            </div>
            <h1 className="max-w-3xl text-5xl font-semibold leading-tight text-white md:text-7xl">
              Munshi AI: Aapki Factory ka Digital Dimag.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-zinc-300">
              Production se Collection tak, sab AI ke bharose. Paper cup factory ke hisaab, stock, sales aur vasooli ko ek hi smart system mein chalao.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link className="rounded-md bg-[#B2FF59] px-6 py-3 text-sm font-bold text-[#07100f] shadow-[0_0_34px_rgba(178,255,89,.35)] hover:bg-white" to="/login">
                Try Now
              </Link>
              <a className="rounded-md border border-white/15 px-6 py-3 text-sm font-semibold text-zinc-100 hover:border-[#B2FF59]/60 hover:text-[#B2FF59]" href="#features">
                Dekho Features
              </a>
            </div>
          </div>

          <div className="relative mx-auto aspect-square w-full max-w-[520px]">
            <div className="absolute inset-8 rounded-full border border-[#B2FF59]/20 bg-[#004D40]/20 blur-3xl" />
            <div className="munshi-float relative grid h-full place-items-center">
              <RoboticMunshi />
            </div>
          </div>
        </section>

        <section id="features" className="mx-auto max-w-7xl px-4 py-20 lg:px-8">
          <div className="mb-10 max-w-2xl">
            <p className="text-sm font-semibold uppercase tracking-widest text-[#B2FF59]">Features</p>
            <h2 className="mt-3 text-3xl font-semibold text-white md:text-4xl">Factory ke liye AI Munshi, sirf software nahi.</h2>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {features.map((feature) => (
              <article key={feature.title} className="rounded-lg border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur transition hover:-translate-y-1 hover:border-[#B2FF59]/50">
                <feature.icon className="h-8 w-8 text-[#B2FF59]" />
                <h3 className="mt-5 text-xl font-semibold">{feature.title}</h3>
                <p className="mt-3 text-sm leading-6 text-zinc-400">{feature.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="pricing" className="mx-auto max-w-7xl px-4 py-20 lg:px-8">
          <div className="rounded-lg border border-[#B2FF59]/25 bg-[#004D40]/35 p-8 shadow-[0_0_60px_rgba(0,77,64,.35)] md:p-10">
            <p className="text-sm font-semibold uppercase tracking-widest text-[#B2FF59]">Pricing</p>
            <div className="mt-4 grid gap-6 md:grid-cols-[1fr_auto] md:items-end">
              <div>
                <h2 className="text-3xl font-semibold">Pay-as-you-Scale</h2>
                <p className="mt-3 max-w-2xl text-zinc-300">Chhoti factory se multi-machine setup tak. Jitna kaam, utna plan. No heavy setup drama.</p>
              </div>
              <Link className="rounded-md bg-white px-5 py-3 text-center text-sm font-bold text-[#07100f] hover:bg-[#B2FF59]" to="/login">
                Start Trial
              </Link>
            </div>
          </div>
        </section>

        <section id="about" className="mx-auto max-w-7xl px-4 py-20 lg:px-8">
          <div className="mb-10 max-w-2xl">
            <p className="text-sm font-semibold uppercase tracking-widest text-[#B2FF59]">Login Portal</p>
            <h2 className="mt-3 text-3xl font-semibold">Apna role choose karo, same secure login se andar jao.</h2>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {roles.map((role) => (
              <Link key={role.title} className="rounded-lg border border-white/10 bg-zinc-950/60 p-6 transition hover:-translate-y-1 hover:border-[#B2FF59]/60 hover:bg-zinc-900" to="/login">
                <role.icon className="h-9 w-9 text-[#B2FF59]" />
                <h3 className="mt-5 text-xl font-semibold">{role.title}</h3>
                <p className="mt-3 text-sm leading-6 text-zinc-400">{role.text}</p>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

function RoboticMunshi() {
  return (
    <div className="relative h-[420px] w-[320px]">
      <div className="absolute left-1/2 top-0 h-20 w-44 -translate-x-1/2 rounded-t-[48px] rounded-bl-[18px] rounded-br-[18px] border border-[#B2FF59]/40 bg-[#004D40] shadow-[0_0_34px_rgba(178,255,89,.18)]">
        <div className="absolute left-1/2 top-3 h-9 w-56 -translate-x-1/2 rounded-full border border-[#B2FF59]/30 bg-[#0f2b28]" />
        <div className="absolute left-1/2 top-8 h-6 w-36 -translate-x-1/2 rounded-full bg-[#B2FF59]/80 blur-sm" />
      </div>
      <div className="absolute left-1/2 top-20 h-32 w-44 -translate-x-1/2 rounded-[36px] border border-white/15 bg-gradient-to-b from-zinc-300 to-zinc-700 shadow-2xl">
        <div className="absolute left-8 top-12 h-4 w-4 rounded-full bg-[#B2FF59] shadow-[0_0_18px_rgba(178,255,89,.85)]" />
        <div className="absolute right-8 top-12 h-4 w-4 rounded-full bg-[#B2FF59] shadow-[0_0_18px_rgba(178,255,89,.85)]" />
        <div className="absolute left-1/2 top-20 h-2 w-20 -translate-x-1/2 rounded-full bg-zinc-900" />
      </div>
      <div className="absolute left-1/2 top-52 h-40 w-56 -translate-x-1/2 rounded-[40px] border border-white/10 bg-gradient-to-br from-zinc-800 via-zinc-700 to-[#004D40] shadow-[0_0_50px_rgba(0,77,64,.45)]">
        <div className="absolute left-1/2 top-7 grid h-20 w-28 -translate-x-1/2 place-items-center rounded-md border border-[#B2FF59]/25 bg-zinc-950/70 text-center text-xs font-semibold text-[#B2FF59]">
          DIGITAL
          <br />
          BAHI
        </div>
      </div>
      <div className="absolute left-0 top-60 h-24 w-16 rotate-[-18deg] rounded-full border border-white/10 bg-zinc-700" />
      <div className="absolute right-0 top-60 h-24 w-16 rotate-[18deg] rounded-full border border-white/10 bg-zinc-700" />
      <div className="absolute bottom-0 left-24 h-28 w-14 rounded-full bg-zinc-700" />
      <div className="absolute bottom-0 right-24 h-28 w-14 rounded-full bg-zinc-700" />
    </div>
  );
}
