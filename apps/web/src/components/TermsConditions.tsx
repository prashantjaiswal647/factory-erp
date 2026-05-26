import React, { useState } from "react";

export default function TermsConditions() {
  const [activeSection, setActiveSection] = useState("agreement");

  const sections = [
    { id: "agreement", title: "1. Scope & Binding Agreement" },
    { id: "account-ownership", title: "2. Account Security & Verification" },
    { id: "licensing", title: "3. Scope of License & Use" },
    { id: "liability-waiver", title: "4. Liability Waiver & Uptime Commitments" },
    { id: "term-termination", title: "5. Terms, Modifications & Termination" },
    { id: "disputes", title: "6. Governing Law & Dispute Resolution" },
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
                Terms of Service
              </span>
              <span className="text-xs text-[#4B5563]">Last Updated: May 26, 2026</span>
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight text-[#111827] sm:text-4xl">
              Terms &amp; Conditions
            </h1>
            <p className="mt-2 text-sm text-[#4B5563]">
              Product: <span className="font-semibold text-[#6D28D9]">MunshiAI</span> | Managed by <span className="font-semibold text-[#4C1D95]">Cosmic Yog</span>
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
              Print Terms
            </button>
            <a
              href="mailto:legal@cosmicyog.com?subject=MunshiAI%20Terms%20Inquiry"
              className="inline-flex items-center justify-center rounded-lg bg-[#6D28D9] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#4C1D95] transition-all duration-200"
            >
              Legal Inquiry
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
            <section id="agreement" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                1. Scope &amp; Binding Agreement
              </h2>
              <p className="mb-4">
                These Terms and Conditions constitute a legally binding agreement made between you, whether personally or on behalf of an 
                incorporated business, manufacturing syndicate, or factory (referred to as the "User", "Licensee", or "you"), and 
                <strong> Cosmic Yog</strong> ("Company", "we", "us", or "our"), concerning your access to and use of the 
                <strong> MunshiAI</strong> software application, cloud interface, and integration portals.
              </p>
              <p>
                By checking boxes, initiating a trial tier registration, or logging into the active software deployment, you explicitly 
                represent that you have read, understood, and consented to be bound by all of these Terms. If you do not agree to 
                be governed by this contract, access is immediately revoked, and you must terminate all utilization of our systems.
              </p>
            </section>

            {/* Section 2 */}
            <section id="account-ownership" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                2. Account Security &amp; Verification
              </h2>
              <p className="mb-4">
                To maintain the high-fidelity security standards required for industrial and transactional ERP databases, all operator accounts, 
                supervisors, and administrative staff profiles must be validated. Our primary authentication layer utilizes:
              </p>
              
              <div className="my-5 rounded-xl border border-[#F5E6D3] bg-[#FFF7ED] p-5">
                <h4 className="font-semibold text-[#4C1D95] text-sm mb-2">Primary Verification Methods</h4>
                <ul className="list-disc pl-5 space-y-2 text-xs sm:text-sm text-[#4B5563]">
                  <li><strong>Phone + Password Authentication:</strong> Multi-factor verification tied to verified corporate mobile connections.</li>
                  <li><strong>Google OAuth Verification:</strong> Single sign-on authentication integrated via secure OAuth 2.0 pipelines.</li>
                </ul>
              </div>

              <p className="mb-4">
                The designated <strong>Factory Manager</strong> or primary workspace subscriber is <strong>solely responsible</strong> for maintaining 
                the strict confidentiality of team access credentials, credentials provisioning, and active API tokens. 
              </p>
              <p>
                Cosmic Yog shall not be responsible or legally liable for unauthorized system entries, data modification, or leaks occurring 
                from local password compromise, supervisor-level credential sharing, or negligence in auditing active factory access keys.
              </p>
            </section>

            {/* Section 3 */}
            <section id="licensing" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                3. Scope of License &amp; Use
              </h2>
              <p className="mb-4">
                Subject to continued tier-fee compliance, Cosmic Yog grants the subscriber a limited, revocable, non-exclusive, non-transferable 
                license to use the features of MunshiAI exclusively for the management of the licensee's own factory workflows, accounting logs, 
                invoice creations, and raw materials analytics.
              </p>
              <p>
                You may not: (a) reverse-engineer or attempt to extract source codes from the compilation packages; (b) share access with 
                competing business entities; or (c) leverage the OpenClaw integrations or local AI models to build a generic competitor software 
                or secondary commercial application.
              </p>
            </section>

            {/* Section 4 */}
            <section id="liability-waiver" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                4. Liability Waiver &amp; Uptime Commitments
              </h2>
              
              <div className="my-6 rounded-xl border-l-4 border-amber-500 bg-amber-50 p-5 shadow-sm">
                <h4 className="font-bold text-[#111827] mb-2 uppercase tracking-wide text-xs text-amber-800">
                  IMPORTANT LEGAL NOTICE: Uptime &amp; Indemnity Waiver
                </h4>
                <p className="text-xs sm:text-sm text-amber-900 leading-relaxed font-semibold">
                  "Under no circumstances shall Cosmic Yog or MunshiAI be held legally liable to you or any third party for temporary factory operational losses, supply-chain disruptions, production down-time, payroll calculation errors, or data synchronization delays resulting from scheduled server maintenance, security upgrades, network dropouts, or third-party uptime issues (including but not limited to hosting providers, database clusters, or OpenClaw AI gateway failures)."
                </p>
              </div>

              <p className="mb-4">
                We make reasonable commercial efforts to guarantee 99.9% uptime, but B2B software relies heavily on remote internet routes and external APIs. 
                Licensee explicitly acknowledges that they maintain standalone local emergency contingency plans for physical shop floor management and 
                worker log backups in case of brief service interruptions.
              </p>
            </section>

            {/* Section 5 */}
            <section id="term-termination" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                5. Terms, Modifications &amp; Termination
              </h2>
              <p className="mb-4">
                These terms will remain in active effect while you use the Service. We reserve the absolute right, in our sole discretion 
                and without notice or financial liability, to suspend, disable, or terminate workspaces that breach billing deadlines, 
                violate licensing restrictions, or present operational security hazards to our shared servers.
              </p>
              <p>
                We may revise these Terms and Conditions periodically to adjust for regulatory changes or product enhancements. Subscribing managers 
                will receive digital notifications upon significant updates. Continuous use of the Service following revisions constitutes formal 
                acceptance of modified terms.
              </p>
            </section>

            {/* Section 6 */}
            <section id="disputes" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                6. Governing Law &amp; Dispute Resolution
              </h2>
              <p className="mb-4">
                These Terms and Conditions and your use of the Service are governed by and construed in accordance with the laws of the jurisdiction 
                under which <strong>Cosmic Yog</strong> is legally incorporated, without regard to conflict of law principles. 
              </p>
              <p>
                Any legal actions, arbitration proceedings, or contract dispute negotiations arising directly out of your commercial usage of MunshiAI 
                shall be settled exclusively in the designated arbitration courts of Cosmic Yog's registered corporate domicile.
              </p>
            </section>

          </div>
        </div>

        {/* Footer print-only watermark */}
        <div className="hidden print:block mt-12 text-center text-xs text-gray-400 border-t pt-4">
          MunshiAI Terms &amp; Conditions • Cosmic Yog Legal Compliance Department • Printed from secure server.
        </div>
      </div>
    </div>
  );
}
