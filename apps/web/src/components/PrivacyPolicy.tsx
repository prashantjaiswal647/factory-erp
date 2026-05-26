import React, { useState } from "react";

export default function PrivacyPolicy() {
  const [activeSection, setActiveSection] = useState("introduction");

  const sections = [
    { id: "introduction", title: "1. Corporate Context & Scope" },
    { id: "data-isolation", title: "2. Multi-tenancy Isolation (factory_id)" },
    { id: "ai-processing", title: "3. AI Data Compliance (OpenClaw & n8n)" },
    { id: "information-collection", title: "4. Information We Collect" },
    { id: "data-retention", title: "5. Retention & Purging" },
    { id: "contact", title: "6. Legal & Support Contact" },
  ];

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="min-h-screen bg-[#FFF7ED] py-12 px-4 sm:px-6 lg:px-8 print:bg-white print:py-0 print:px-0">
      <div className="mx-auto max-w-6xl rounded-2xl bg-white p-6 shadow-xl border border-[#F5E6D3] print:shadow-none print:border-none print:p-0">
        
        {/* Header Section */}
        <div className="border-b border-[#F5E6D3] pb-8 mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center rounded-md bg-[#F3E8FF] px-2 py-1 text-xs font-semibold text-[#6D28D9] ring-1 ring-inset ring-[#6D28D9]/10">
                Legal Compliance
              </span>
              <span className="text-xs text-[#4B5563]">Last Updated: May 26, 2026</span>
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight text-[#111827] sm:text-4xl">
              Privacy Policy
            </h1>
            <p className="mt-2 text-sm text-[#4B5563]">
              Product: <span className="font-semibold text-[#6D28D9]">MunshiAI</span> | Owned and operated by <span className="font-semibold text-[#4C1D95]">Cosmic Yog</span>
            </p>
          </div>
          
          <div className="flex items-center gap-3 print:hidden">
            <button
              onClick={handlePrint}
              className="inline-flex items-center justify-center rounded-lg bg-white px-4 py-2 text-sm font-semibold text-[#4C1D95] shadow-sm ring-1 ring-inset ring-[#F5E6D3] hover:bg-[#FFF7ED] transition-all duration-200"
            >
              <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.72 13.89l-2.2 2.2a2.25 2.25 0 00-.01 3.19l.01.01a2.25 2.25 0 003.18 0l2.2-2.2M6.72 13.89l-2.2-2.2a2.25 2.25 0 010-3.18l.01-.01a2.25 2.25 0 013.18 0l2.2 2.2m-5.4 3.19l5.4-5.4M18 10.5a8.25 8.25 0 11-16.5 0 8.25 8.25 0 0116.5 0z" />
              </svg>
              Print Policy
            </button>
            <a
              href="mailto:cosmicyog7@gmail.com?subject=MunshiAI%20Privacy%20Policy%20Inquiry"
              className="inline-flex items-center justify-center rounded-lg bg-[#6D28D9] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#4C1D95] transition-all duration-200"
            >
              Contact Legal
            </a>
          </div>
        </div>

        {/* Content Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          
          {/* Table of Contents - Sidebar */}
          <div className="lg:col-span-1 print:hidden">
            <div className="sticky top-6 rounded-xl bg-[#FFF7ED] p-4 border border-[#F5E6D3]">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[#4C1D95] mb-4">
                Table of Contents
              </h2>
              <nav className="space-y-1">
                {sections.map((section) => (
                  <a
                    key={section.id}
                    href={`#${section.id}`}
                    onClick={() => setActiveSection(section.id)}
                    className={`block w-full text-left rounded-lg px-3 py-2 text-xs font-medium transition-all duration-150 ${
                      activeSection === section.id
                        ? "bg-[#6D28D9] text-white shadow-md"
                        : "text-[#4B5563] hover:bg-[#F3E8FF] hover:text-[#4C1D95]"
                    }`}
                  >
                    {section.title}
                  </a>
                ))}
              </nav>
            </div>
          </div>

          {/* Legal Text Column */}
          <div className="lg:col-span-3 text-[#111827] space-y-8 leading-relaxed text-sm sm:text-base print:lg:col-span-4">
            
            {/* Section 1 */}
            <section id="introduction" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                1. Corporate Context &amp; Scope
              </h2>
              <p className="mb-4">
                This Privacy Policy describes the policies and procedures of <strong>Cosmic Yog</strong> (hereinafter referred to as the 
                "Company", "we", "us", or "our"), under the sole proprietorship of <strong>PRASHANT</strong>, with its physical headquarters and 
                registered corporate office located at <strong>K46/189 hartirath varanasi 221001, VARANASI, 221001, Uttar Pradesh</strong>, operating 
                the digital enterprise software application <strong>MunshiAI</strong> (the "Service" or "Product").
              </p>
              <p>
                By registering, licensing, or accessing the Service, the subscribing business entity and its designated representatives, managers, 
                and operators agree to the data collection and operational security frameworks set forth herein.
              </p>
            </section>

            {/* Section 2 */}
            <section id="data-isolation" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                2. Database &amp; Multi-tenancy Isolation (factory_id)
              </h2>
              <div className="rounded-xl bg-purple-50 p-5 border border-[#F3E8FF] mb-4">
                <h3 className="text-sm font-semibold text-[#4C1D95] uppercase tracking-wide mb-2">
                  Technical Safeguard: Logical Multi-Tenancy segregation
                </h3>
                <p className="text-xs sm:text-sm text-[#4B5563]">
                  All raw materials, inventory sheets, machine logs, shift timelines, and daily worker entries are strictly segregated at the logical database level. We enforce parameterized <code>factory_id</code> verification checks on all database transaction requests to guarantee that data remains completely locked and inaccessible to other customer tenants.
                </p>
              </div>
              <p className="mb-4">
                This strict tenant segmentation blocks unauthorized lateral data traversal, API leaks, or accidental horizontal privilege escalations, keeping your factory intelligence and private metrics safe inside your registered business branch.
              </p>
            </section>

            {/* Section 3 */}
            <section id="ai-processing" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                3. AI Data Compliance (OpenClaw &amp; n8n)
              </h2>
              <p className="mb-4">
                MunshiAI routes user operational queries, wastage indicators, and production logs through state-of-the-art Large Language Models (LLMs) via our secure <strong>OpenClaw</strong> gateway and automated <strong>n8n</strong> pipelines.
              </p>
              
              <div className="my-6 rounded-xl border-l-4 border-[#6D28D9] bg-[#FFF7ED] p-5 shadow-sm">
                <h4 className="font-bold text-[#111827] mb-2">The Zero-Cache AI Transaction Commitment</h4>
                <p className="text-xs sm:text-sm text-[#4B5563] leading-relaxed">
                  We explicitly declare that all customer factory metrics, raw materials volume data, and ledger records processed via third-party AI interfaces, OpenClaw, or automated n8n pipelines are <strong>strictly transient</strong>.
                </p>
                <ul className="mt-3 list-disc pl-5 space-y-1 text-xs sm:text-sm text-[#4B5563]">
                  <li><strong>No Cached Stores:</strong> Transmitted metrics are kept in memory only for the duration of the query execution and are never cached or written to persistent third-party disks.</li>
                  <li><strong>No Training Use:</strong> All sent payload metrics are strictly excluded from external foundation model re-training, weight optimization, or general AI training datasets.</li>
                </ul>
              </div>
            </section>

            {/* Section 4 */}
            <section id="information-collection" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                4. Information We Collect
              </h2>
              <p className="mb-4">
                To operate the Service under Cosmic Yog, we compile specific data sets necessary for billing, authentication, and 
                daily enterprise operations:
              </p>
              <ul className="list-decimal pl-5 mb-4 space-y-2">
                <li>
                  <strong className="text-[#4C1D95]">User Identity:</strong> Registered phone numbers, password hashes, and user profiles.
                </li>
                <li>
                  <strong className="text-[#4C1D95]">Factory Telemetry:</strong> Machine numbers, mold sizes, shift performance data, raw material inputs, and worker registries.
                </li>
              </ul>
            </section>

            {/* Section 5 */}
            <section id="data-retention" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                5. Retention &amp; Purging
              </h2>
              <p className="mb-4">
                Your data is retained as long as your enterprise subscription with Cosmic Yog remains active. If a factory manager 
                initiates a profile termination or subscription cancellation, the system will retain tenant assets for a grace period 
                of thirty (30) days, after which all database rows tied to your <code>factory_id</code> will be systematically purged.
              </p>
            </section>

            {/* Section 6 */}
            <section id="contact" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                6. Legal &amp; Support Contact
              </h2>
              <p className="mb-4">
                For questions regarding database isolation validations, OpenClaw API data handling guarantees, or other legal inquiries, please contact our compliance office:
              </p>
              <div className="rounded-xl bg-[#FFF7ED] p-5 border border-[#F5E6D3] text-xs sm:text-sm">
                <p className="font-bold text-[#4C1D95]">Cosmic Yog Legal Department</p>
                <p>Proprietor: PRASHANT</p>
                <p>Address: K46/189 hartirath varanasi 221001, VARANASI, 221001, Uttar Pradesh</p>
                <p>Email: <a href="mailto:cosmicyog7@gmail.com" className="text-[#6D28D9] hover:underline">cosmicyog7@gmail.com</a></p>
                <p>Phone: <span className="font-semibold text-[#111827]">8285811727</span></p>
              </div>
            </section>

          </div>
        </div>
      </div>
    </div>
  );
}
