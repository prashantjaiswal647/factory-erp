import {
  ArrowRight,
  BarChart3,
  BellRing,
  Boxes,
  Check,
  ChevronDown,
  CreditCard,
  Factory,
  FileText,
  Menu,
  PackageCheck,
  ReceiptText,
  TrendingUp,
  UsersRound,
  X,
  Zap
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import PricingPlansSection from "../components/PricingPlansSection";
import heroImage from "../assets/munshi-ai-hero-final.png";
import mobileHeroImage from "../assets/munshi-ai-hero-mobile.png";

const navLinks = [
  { label: "Features", href: "#features" },
  { label: "Industries", href: "#industries" },
  { label: "Pricing", href: "#pricing" },
  { label: "Testimonials", href: "#testimonials" }
];

const heroBadges = [
  { icon: Factory, title: "Production Tracking" },
  { icon: Boxes, title: "Inventory Management" },
  { icon: CreditCard, title: "Finance & Payments" },
  { icon: FileText, title: "E-Invoicing" },
  { icon: BarChart3, title: "AI Production Charts" },
  { icon: Zap, title: "AI Insights & Reports" }
];

const features = [
  { icon: ReceiptText, title: "Daily Production Entry", text: "Roz ka production, machine aur shift data simple form se record karein." },
  { icon: TrendingUp, title: "Wastage Calculation", text: "Material wastage aur cost leakage ko automatic track karein." },
  { icon: Boxes, title: "Raw Material Inventory", text: "Blank, roll, chemical, packaging ya raw stock ka live hisaab." },
  { icon: PackageCheck, title: "Finished Goods Stock", text: "Ready maal, boxes aur dispatch stock par clear visibility." },
  { icon: FileText, title: "E-Invoicing", text: "Invoice, GST-ready records aur customer billing ek jagah." },
  { icon: BellRing, title: "Payment Reminder", text: "Pending payment aur customer follow-up ke liye smart alerts." },
  { icon: BarChart3, title: "AI Enabled Production Charts", text: "Production trend, downtime aur output ko visual charts mein dekhein." },
  { icon: UsersRound, title: "Worker & Machine Performance", text: "Staff, machine aur shift performance ko compare karein." },
  { icon: Zap, title: "n8n Automation", text: "WhatsApp, reminders, reports aur backend workflows automate karein." }
];

const industries = ["Paper Cup Manufacturing", "Paper Glass Manufacturing", "Disposable Packaging Units"];

const positioningCards = [
  {
    icon: Factory,
    title: "Machinery Friendly ERP",
    text: "For production units where machine-wise output, wastage and daily performance matter."
  },
  {
    icon: PackageCheck,
    title: "Paper Cup Ready",
    text: "Pre-configured workflows for paper cup, paper glass, raw material, bottom roll, packing and dispatch."
  },
  {
    icon: BarChart3,
    title: "AI Powered Reports",
    text: "Production trends, payment reminders, inventory alerts and business insights in one dashboard."
  }
];

export default function LandingPage() {
  const [open, setOpen] = useState(false);
  const [resourcesOpen, setResourcesOpen] = useState(false);

  return (
    <main className="min-h-screen bg-[#FFF7ED] text-[#111827]">
      <header className="sticky top-0 z-40 border-b border-[#E5E7EB] bg-white/90 backdrop-blur-xl">
        <nav className="mx-auto flex h-20 max-w-7xl items-center justify-between px-4 lg:px-8">
          <Link className="flex items-center gap-3" to="/">
            <div className="grid h-11 w-11 place-items-center rounded-full border border-[#E5E7EB] bg-[#FFF7ED] text-[#4C1D95]">
              <span className="text-xl font-black">म</span>
            </div>
            <div>
              <p className="text-2xl font-black leading-6 tracking-tight">MUNSHI <span className="text-[#6D28D9]">AI</span></p>
              <p className="text-xs font-semibold text-[#4C1D95]">AI-Powered Factory ERP</p>
            </div>
          </Link>

          <div className="hidden items-center gap-8 text-sm font-medium text-[#111827] md:flex">
            {navLinks.map((item) => (
              <a key={item.href} className="transition hover:text-[#6D28D9]" href={item.href}>
                {item.label}
              </a>
            ))}
            <div className="relative">
              <button 
                className="inline-flex items-center gap-1 transition hover:text-[#6D28D9] focus:outline-none" 
                type="button"
                onClick={() => setResourcesOpen((prev) => !prev)}
                onBlur={() => setTimeout(() => setResourcesOpen(false), 200)}
              >
                Resources <ChevronDown className="h-3.5 w-3.5" />
              </button>
              {resourcesOpen && (
                <div className="absolute right-0 mt-3 w-56 origin-top-right rounded-xl border border-[#F5E6D3] bg-white p-2 shadow-xl ring-1 ring-black/5 animate-in fade-in slide-in-from-top-2 duration-150">
                  <div className="text-xs font-semibold uppercase tracking-wider text-[#4C1D95] px-3 py-2 border-b border-[#FFF7ED] mb-1">
                    Legal &amp; Compliance
                  </div>
                  <Link to="/privacy-policy" className="flex items-center rounded-lg px-3 py-2 text-sm text-[#4B5563] hover:bg-[#F3E8FF] hover:text-[#6D28D9] transition-all">
                    Privacy Policy
                  </Link>
                  <Link to="/terms-conditions" className="flex items-center rounded-lg px-3 py-2 text-sm text-[#4B5563] hover:bg-[#F3E8FF] hover:text-[#6D28D9] transition-all">
                    Terms &amp; Conditions
                  </Link>
                  <Link to="/refund-policy" className="flex items-center rounded-lg px-3 py-2 text-sm text-[#4B5563] hover:bg-[#F3E8FF] hover:text-[#6D28D9] transition-all">
                    Refund &amp; Cancellation
                  </Link>
                </div>
              )}
            </div>
          </div>

          <div className="hidden items-center gap-5 md:flex">
            <Link className="text-sm font-semibold text-[#111827] hover:text-[#6D28D9]" to="/login">
              Login
            </Link>
            <Link className="rounded-lg bg-[#6D28D9] px-6 py-3 text-sm font-bold text-white shadow-lg shadow-purple-200 transition hover:bg-[#4C1D95]" to="/login">
              Book a Demo
            </Link>
          </div>

          <button className="grid h-10 w-10 place-items-center rounded-lg border border-[#E5E7EB] text-[#111827] md:hidden" type="button" onClick={() => setOpen((value) => !value)}>
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </nav>

        {open ? (
          <div className="border-t border-[#E5E7EB] bg-white px-4 py-4 md:hidden">
            <div className="grid gap-3 text-sm font-semibold text-[#111827]">
              {navLinks.map((item) => (
                <a key={item.href} href={item.href} onClick={() => setOpen(false)}>
                  {item.label}
                </a>
              ))}
              <div className="border-t border-[#FFF7ED] my-2 pt-2">
                <p className="text-xs font-bold uppercase tracking-wider text-[#4C1D95] mb-2 px-1">Legal</p>
                <div className="grid gap-2 pl-2">
                  <Link to="/privacy-policy" className="text-[#4B5563] hover:text-[#6D28D9]" onClick={() => setOpen(false)}>Privacy Policy</Link>
                  <Link to="/terms-conditions" className="text-[#4B5563] hover:text-[#6D28D9]" onClick={() => setOpen(false)}>Terms &amp; Conditions</Link>
                  <Link to="/refund-policy" className="text-[#4B5563] hover:text-[#6D28D9]" onClick={() => setOpen(false)}>Refund Policy</Link>
                </div>
              </div>
              <Link className="rounded-lg border border-[#E5E7EB] px-4 py-2 text-center" to="/login">Login</Link>
              <Link className="rounded-lg bg-[#6D28D9] px-4 py-2 text-center text-white" to="/login">Book a Demo</Link>
            </div>
          </div>
        ) : null}
      </header>

      <section className="relative overflow-hidden border-b border-[#E5E7EB] bg-[#FFF7ED] md:min-h-[760px]">
        <img
          className="absolute inset-0 hidden h-full w-full object-cover object-right md:block"
          src={heroImage}
          alt=""
          aria-hidden="true"
        />
        <div className="absolute inset-0 hidden bg-[linear-gradient(90deg,rgba(255,247,237,0.98)_0%,rgba(255,247,237,0.92)_32%,rgba(255,247,237,0.60)_48%,rgba(255,247,237,0.18)_65%,rgba(255,247,237,0)_82%)] md:block" />
        <div className="absolute inset-0 hidden bg-[radial-gradient(circle_at_14%_12%,rgba(243,232,255,.55),transparent_30%)] md:block" />
        <div className="relative z-10 flex max-w-7xl flex-col px-[18px] py-6 md:min-h-[760px] md:justify-start md:px-0 md:py-0">
          <div className="bg-[#FFF7ED]/95 md:ml-10 md:max-w-[560px] md:bg-transparent md:pt-[84px] md:text-left lg:ml-[96px] lg:max-w-[600px] lg:pt-[90px] xl:ml-[120px]">
            <div className="mb-5 inline-flex rounded-full bg-white/90 px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-[#4C1D95] shadow-sm sm:text-sm md:bg-white/85 md:tracking-[0.18em]">
              AI Powered • Factory Supervisor ERP
            </div>
            <h1 className="text-[38px] font-black leading-[1.05] tracking-tight text-[#111827] sm:text-[42px] md:text-5xl xl:text-7xl">
              Aapka Digital <span className="text-[#6D28D9]">Munshi.</span> Aapka Business Smart.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-[#4B5563] md:mt-6 md:text-lg md:leading-8">
              AI-powered ERP for machinery-based manufacturing units — production, inventory, finance, worker management, e-invoicing aur AI reports sab kuch ek jagah.
            </p>
            <p className="mt-4 max-w-xl rounded-xl border border-purple-100 bg-white px-4 py-3 text-sm font-bold leading-6 text-[#4C1D95] shadow-sm md:bg-white/80">
              Currently ready-to-use and specially crafted for Paper Cup & Paper Glass manufacturing industry.
            </p>

            <div className="mt-7 grid max-w-2xl grid-cols-1 gap-3 rounded-xl border border-[#E5E7EB] bg-white p-3 shadow-xl shadow-orange-100/70 min-[390px]:grid-cols-2 md:mt-8 md:bg-white/90 xl:grid-cols-3">
              {heroBadges.map((badge) => (
                <div key={badge.title} className="flex items-center gap-3 rounded-lg px-2 py-2">
                  <badge.icon className="h-6 w-6 text-[#6D28D9]" />
                  <div>
                    <p className="text-sm font-bold text-[#111827]">{badge.title}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-7 flex flex-col gap-3 sm:flex-row md:mt-8">
              <Link className="inline-flex h-14 w-full items-center justify-center gap-3 rounded-lg bg-[#6D28D9] px-8 text-base font-bold text-white shadow-lg shadow-purple-200 transition hover:bg-[#4C1D95] sm:w-auto" to="/login">
                Start Free Trial
                <ArrowRight className="h-5 w-5" />
              </Link>
              <Link className="inline-flex h-14 w-full items-center justify-center rounded-lg border border-[#6D28D9] bg-white px-8 text-base font-bold text-[#6D28D9] transition hover:bg-[#F3E8FF] sm:w-auto md:bg-white/70" to="/login">
                Book a Demo
              </Link>
            </div>
          </div>

          <img
            className="mt-6 block w-full rounded-2xl object-cover object-top shadow-2xl shadow-orange-100 md:hidden"
            src={mobileHeroImage}
            alt="Munshi AI robot working inside a factory office"
          />
        </div>
      </section>

      <PricingPlansSection className="pt-14" source="landing" />

      <section className="mx-auto max-w-7xl px-4 py-16 lg:px-8">
        <SectionHeader
          eyebrow="Positioning"
          title="Built for Machinery Manufacturing. Ready for Paper Cup Industry."
          text="Munshi AI is designed for factories where machines, raw material, wastage, production speed, workers, inventory and payments must be tracked daily. The current ready-to-use version is specially crafted for paper cup and paper glass manufacturing units, with workflows that match their real factory operations."
        />
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {positioningCards.map((card) => (
            <article key={card.title} className="rounded-2xl border border-[#E5E7EB] bg-white p-6 shadow-sm shadow-orange-100/70">
              <div className="grid h-12 w-12 place-items-center rounded-xl bg-[#F3E8FF] text-[#6D28D9]">
                <card.icon className="h-6 w-6" />
              </div>
              <h3 className="mt-5 text-lg font-black text-[#111827]">{card.title}</h3>
              <p className="mt-3 text-sm leading-6 text-[#4B5563]">{card.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="features" className="mx-auto max-w-7xl px-4 py-20 lg:px-8">
        <SectionHeader eyebrow="Features" title="Factory ka daily kaam ab simple aur smart." text="Munshi AI aapke production floor, godown, accounts aur worker data ko ek connected ERP mein laata hai." />
        <div className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <article key={feature.title} className="rounded-2xl border border-[#E5E7EB] bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-xl hover:shadow-purple-100">
              <div className="grid h-12 w-12 place-items-center rounded-xl bg-[#F3E8FF] text-[#6D28D9]">
                <feature.icon className="h-6 w-6" />
              </div>
              <h3 className="mt-5 text-lg font-black text-[#111827]">{feature.title}</h3>
              <p className="mt-3 text-sm leading-6 text-[#4B5563]">{feature.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="bg-[#F5E6D3]/55">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-20 lg:grid-cols-[0.9fr_1.1fr] lg:px-8 lg:items-center">
          <SectionHeader eyebrow="Dashboard Preview" title="Charts, alerts aur pending payments ek hi screen par." text="Owner ko production trend, pending payment aur inventory alerts turant dikhte hain — bina Excel ke." />
          <div className="rounded-3xl border border-[#E5E7EB] bg-white p-5 shadow-2xl shadow-orange-100">
            <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-2xl bg-[#F3E8FF] p-5">
                <div className="mb-4 flex items-center justify-between">
                  <p className="font-black text-[#111827]">AI Production Charts</p>
                  <BarChart3 className="h-5 w-5 text-[#6D28D9]" />
                </div>
                <div className="flex h-52 items-end gap-3">
                  {[42, 66, 54, 80, 68, 96, 76, 88].map((height, index) => (
                    <span key={`${height}-${index}`} className="flex-1 rounded-t-lg bg-[#6D28D9]" style={{ height: `${height}%` }} />
                  ))}
                </div>
              </div>
              <div className="grid gap-4">
                <MetricCard label="Pending Payments" value="₹2.4L" tone="warning" />
                <MetricCard label="Inventory Alerts" value="8 Items" tone="error" />
                <MetricCard label="Today Production" value="18,420 pcs" tone="success" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="industries" className="mx-auto max-w-7xl px-4 py-20 lg:px-8">
        <SectionHeader eyebrow="Industries" title="Local manufacturing units ke liye bana ERP." text="Munshi AI Indian factories ki real language, real workflows aur real problems ko samajhta hai." />
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {industries.map((industry) => (
            <div key={industry} className="rounded-2xl border border-[#E5E7EB] bg-white p-6 shadow-sm">
              <Factory className="h-8 w-8 text-[#6D28D9]" />
              <h3 className="mt-5 text-lg font-black text-[#111827]">{industry}</h3>
              <p className="mt-3 text-sm leading-6 text-[#4B5563]">Production, stock, billing aur worker tracking ke liye ready workflow.</p>
            </div>
          ))}
        </div>
      </section>

      <section id="testimonials" className="bg-white border-b border-[#E5E7EB]">
        <div className="mx-auto max-w-7xl px-4 py-16 lg:px-8">
          <div className="rounded-3xl border border-[#E5E7EB] bg-[#FFF7ED] p-8 shadow-sm">
            <p className="text-center text-xl font-black text-[#111827] md:text-2xl">
              “Pehle production, stock aur payment alag-alag diary mein tha. Munshi AI se owner ko poora factory status mobile par mil jata hai.”
            </p>
            <p className="mt-4 text-center text-sm font-semibold text-[#6D28D9]">Indian Factory Owner Feedback</p>
          </div>
        </div>
      </section>

      {/* Premium Footer with Compliance Links */}
      <footer className="bg-white py-12 px-4 sm:px-6 lg:px-8 border-t border-[#E5E7EB]">
        <div className="mx-auto max-w-7xl grid grid-cols-1 md:grid-cols-4 gap-8">
          <div className="md:col-span-2">
            <div className="flex items-center gap-3 mb-4">
              <div className="grid h-10 w-10 place-items-center rounded-full border border-[#E5E7EB] bg-[#FFF7ED] text-[#4C1D95]">
                <span className="text-lg font-black">म</span>
              </div>
              <div>
                <p className="text-xl font-black tracking-tight">MUNSHI <span className="text-[#6D28D9]">AI</span></p>
                <p className="text-xs text-[#4B5563]">Operated under parent firm Cosmic Yog</p>
              </div>
            </div>
            <p className="text-sm text-[#4B5563] max-w-sm">
              AI-Powered Factory ERP designed specifically for machinery manufacturing plants. Programmatically secure, isolated, and legally compliant.
            </p>
          </div>

          <div>
            <h4 className="text-sm font-black uppercase tracking-wider text-[#4C1D95] mb-4">Product</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="#features" className="text-[#4B5563] hover:text-[#6D28D9] transition">Features</a></li>
              <li><a href="#industries" className="text-[#4B5563] hover:text-[#6D28D9] transition">Industries</a></li>
              <li><a href="#pricing" className="text-[#4B5563] hover:text-[#6D28D9] transition">Pricing Plans</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-sm font-black uppercase tracking-wider text-[#4C1D95] mb-4">Legal &amp; Compliance</h4>
            <ul className="space-y-2 text-sm">
              <li><Link to="/privacy-policy" className="text-[#4B5563] hover:text-[#6D28D9] transition">Privacy Policy</Link></li>
              <li><Link to="/terms-conditions" className="text-[#4B5563] hover:text-[#6D28D9] transition">Terms &amp; Conditions</Link></li>
              <li><Link to="/refund-policy" className="text-[#4B5563] hover:text-[#6D28D9] transition">Refund Policy</Link></li>
            </ul>
          </div>
        </div>

        <div className="mx-auto max-w-7xl mt-12 pt-8 border-t border-[#E5E7EB] flex flex-col sm:flex-row items-center justify-between text-xs text-[#4B5563] gap-4">
          <p>© {new Date().getFullYear()} Cosmic Yog. All rights reserved.</p>
          <p>Powered by OpenClaw &amp; n8n automation channels.</p>
        </div>
      </footer>
    </main>
  );
}

function SectionHeader({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return (
    <div className="max-w-3xl">
      <p className="text-sm font-black uppercase tracking-wide text-[#6D28D9]">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-[#111827] md:text-4xl">{title}</h2>
      <p className="mt-4 text-base leading-7 text-[#4B5563]">{text}</p>
    </div>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: "success" | "warning" | "error" }) {
  const tones = {
    success: "bg-green-50 text-[#16A34A]",
    warning: "bg-amber-50 text-[#F59E0B]",
    error: "bg-red-50 text-[#DC2626]"
  };

  return (
    <div className="rounded-2xl border border-[#E5E7EB] bg-white p-5">
      <p className="text-sm font-semibold text-[#4B5563]">{label}</p>
      <p className={`mt-3 text-2xl font-black ${tones[tone]}`}>{value}</p>
    </div>
  );
}
