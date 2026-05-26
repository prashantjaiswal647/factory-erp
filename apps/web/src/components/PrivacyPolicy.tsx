import React, { useState } from "react";

export default function PrivacyPolicy() {
  const [activeSection, setActiveSection] = useState("introduction");

  const sections = [
    { id: "introduction", title: "1. Corporate Context & Scope" },
    { id: "data-isolation", title: "2. Database & Factory Data Isolation" },
    { id: "ai-processing", title: "3. AI Processing & Third-Party Gateways" },
    { id: "information-collection", title: "4. Information We Collect" },
    { id: "data-retention", title: "5. Retention & Archiving" },
    { id: "contact", title: "6. Legal & Compliance Contact" },
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
              Product: <span className="font-semibold text-[#6D28D9]">MunshiAI</span> | Operated under parent firm <span className="font-semibold text-[#4C1D95]">Cosmic Yog</span>
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
              href="mailto:compliance@cosmicyog.com?subject=MunshiAI%20Privacy%20Policy%20Inquiry"
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
                1. Corporate Context & Scope
              </h2>
              <p className="mb-4">
                This Privacy Policy describes the policies and procedures of <strong>Cosmic Yog</strong> (hereinafter referred to as the 
                "Company", "we", "us", or "our"), operating the digital enterprise software application <strong>MunshiAI</strong> (the "Service" 
                or "Product"), regarding the collection, processing, security, and containment of operational telemetry, metadata, financial records, 
                and personnel information. 
              </p>
              <p>
                By registering, licensing, or accessing the Service, the subscribing business entity and its designated representatives, managers, 
                and operators agree to the data collection and operational security frameworks set forth herein. If you are entering into this 
                agreement on behalf of a factory, manufacturing facility, or registered enterprise, you declare that you possess the requisite 
                legal authority to bind such entity to these provisions.
              </p>
            </section>

            {/* Section 2 */}
            <section id="data-isolation" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                2. Database & Factory Data Isolation
              </h2>
              <div className="rounded-xl bg-purple-50 p-5 border border-[#F3E8FF] mb-4">
                <h3 className="text-sm font-semibold text-[#4C1D95] uppercase tracking-wide mb-2">
                  Technical Safeguard: Schema-Level Segmentation
                </h3>
                <p className="text-xs sm:text-sm text-[#4B5563]">
                  To guarantee absolute privacy and commercial security, MunshiAI implements a strict multi-tenant data architecture. 
                  All relational database tables, ledger logs, and operational transaction stores enforce parameterized 
                  <code>factory_id</code> verification checks at the physical and logical query building level.
                </p>
              </div>
              <p className="mb-4">
                No request, query, indexing routine, or report compilation may traverse across tenant boundary lines. Every transaction 
                is cryptographically bound to the specific organization's identifier. The system dynamically validates every API authorization 
                against the session's active <code>factory_id</code>, neutralizing any possibility of cross-factory data leaks, accidental 
                spills, or lateral access escalation. 
              </p>
              <p>
                Staff credentials, active sessions, and data storage files associated with one license instance are completely segregated 
                from other customer workspaces. Database isolation rules are checked on every persistent state change, ensuring that your 
                operational metrics and factory assets remain strictly private to your registered corporate branch.
              </p>
            </section>

            {/* Section 3 */}
            <section id="ai-processing" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                3. AI Processing & Third-Party Gateways
              </h2>
              <p className="mb-4">
                MunshiAI leverages state-of-the-art Large Language Models (LLMs) and advanced natural language routing interfaces, 
                primarily via our secure <strong>OpenClaw</strong> third-party AI interface, to analyze factory logs, compute metrics, and answer natural 
                language queries on demand.
              </p>
              
              <div className="my-6 rounded-xl border-l-4 border-[#6D28D9] bg-[#FFF7ED] p-5 shadow-sm">
                <h4 className="font-bold text-[#111827] mb-2">The Zero-Cache AI Transaction Commitment</h4>
                <p className="text-xs sm:text-sm text-[#4B5563] leading-relaxed">
                  We explicitly declare that all customer factory metrics, raw materials volume data, attendance registers, and financial ledger records processed via third-party AI interfaces or the OpenClaw gateway are <strong>strictly transactional</strong>.
                </p>
                <ul className="mt-3 list-disc pl-5 space-y-1 text-xs sm:text-sm text-[#4B5563]">
                  <li><strong>No Cached Stores:</strong> Transmitted metrics and context schemas are kept in memory only for the duration of the query execution and are never cached or written to persistent third-party disks.</li>
                  <li><strong>No Training Use:</strong> All sent payload metrics are strictly excluded from external foundation model re-training, weight optimization, reinforcement learning (RLHF), or general AI development datasets.</li>
                  <li><strong>Encrypted Transport:</strong> Data sent between MunshiAI, OpenClaw, and LLM providers is fully encrypted using TLS 1.3 protocol standards.</li>
                </ul>
              </div>

              <p>
                This transactional parameter ensures that your confidential manufacturing intelligence, proprietary formulation metrics, 
                and payroll structures remain proprietary. Standard processing logs generated by API routes are automatically sanitized 
                to scrub variable numerical outputs and proprietary identifiers.
              </p>
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
                  <strong className="text-[#4C1D95]">User Credentials & Identity Metrics:</strong> Registered phone numbers, 
                  encrypted passwords, and secure tokens received from Google OAuth integrations.
                </li>
                <li>
                  <strong className="text-[#4C1D95]">Factory Operational Telemetry:</strong> Stock logs, production quantities, 
                  raw material invoices, product pricing tiers, machine statuses, and employee timesheets.
                </li>
                <li>
                  <strong className="text-[#4C1D95]">Billing & Subscription Indicators:</strong> Transaction history, current active tier 
                  identifiers, credit card tokens handled securely through PCI-DSS compliant gateways, and historical ledger actions.
                </li>
              </ul>
            </section>

            {/* Section 5 */}
            <section id="data-retention" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                5. Retention & Archiving
              </h2>
              <p className="mb-4">
                Your data is retained as long as your enterprise subscription with Cosmic Yog remains active. If a factory manager 
                initiates a profile termination or subscription cancellation, the system will retain tenant assets for a grace period 
                of thirty (30) days to prevent accidental data loss and permit the export of operational files.
              </p>
              <p>
                Upon the expiration of the retention window, all operational registers, production logs, database rows associated with 
                your specific <code>factory_id</code>, and customer listings will be systematically purged from our active transactional databases. 
                Encrypted database backup snapshots are routinely rotated and will overwrite previous data points within ninety (90) days.
              </p>
            </section>

            {/* Section 6 */}
            <section id="contact" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                6. Legal & Compliance Contact
              </h2>
              <p className="mb-4">
                For questions regarding database isolation validations, OpenClaw API data handling guarantees, or to request a full 
                export of your system registries under GDPR/CCPA framework equivalents, please contact our designated corporate data officer:
              </p>
              <div className="rounded-xl bg-[#FFF7ED] p-5 border border-[#F5E6D3] text-xs sm:text-sm">
                <p className="font-bold text-[#4C1D95]">Cosmic Yog Compliance Office</p>
                <p>Attention: Data Protection & Legal Counsel (MunshiAI)</p>
                <p>Email: <a href="mailto:compliance@cosmicyog.com" className="text-[#6D28D9] hover:underline">compliance@cosmicyog.com</a></p>
                <p className="mt-2 text-xs text-[#4B5563]">Physical address registry available upon formal corporate requests.</p>
              </div>
            </section>

          </div>
        </div>

        {/* Footer print-only watermark */}
        <div className="hidden print:block mt-12 text-center text-xs text-gray-400 border-t pt-4">
          MunshiAI Privacy Policy • Cosmic Yog Legal Compliance Department • Printed directly from secure portal.
        </div>
      </div>
    </div>
  );
}
