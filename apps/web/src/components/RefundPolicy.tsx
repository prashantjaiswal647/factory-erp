import React, { useState } from "react";

export default function RefundPolicy() {
  const [activeSection, setActiveSection] = useState("refund-window");

  const sections = [
    { id: "refund-window", title: "1. 7-Day Refund window" },
    { id: "credit-process", title: "2. Systematic Crediting & Processing" },
    { id: "cancellation", title: "3. B2B Cancellation Guidelines" },
    { id: "tier-modifications", title: "4. Tier Modifications & Upgrades" },
    { id: "ineligible-claims", title: "5. Ineligible Refund Claims" },
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
                Billing &amp; Refunds
              </span>
              <span className="text-xs text-[#4B5563]">Last Updated: May 26, 2026</span>
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight text-[#111827] sm:text-4xl">
              Refund &amp; Cancellation Policy
            </h1>
            <p className="mt-2 text-sm text-[#4B5563]">
              Product: <span className="font-semibold text-[#6D28D9]">MunshiAI</span> | Issued by <span className="font-semibold text-[#4C1D95]">Cosmic Yog</span>
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
              href="mailto:billing@cosmicyog.com?subject=MunshiAI%20Refund%20Claim"
              className="inline-flex items-center justify-center rounded-lg bg-[#6D28D9] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#4C1D95] transition-all duration-200"
            >
              Submit Claim
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
            <section id="refund-window" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                1. 7-Day Refund Window &amp; Eligibility
              </h2>
              <p className="mb-4">
                At Cosmic Yog, we stand behind the operational quality and analytical capability of MunshiAI. To ensure a risk-free 
                onboarding experience for factory administrators, we strictly implement a <strong>7-day money-back guarantee</strong>.
              </p>
              
              <div className="my-5 rounded-xl border border-[#F5E6D3] bg-[#FFF7ED] p-5">
                <h4 className="font-semibold text-[#111827] text-sm mb-2 uppercase tracking-wide">
                  Refund Request Period
                </h4>
                <p className="text-xs sm:text-sm text-[#4B5563] leading-relaxed">
                  Subscribed enterprise accounts can claim a full, 100% refund of fees paid if the claim is submitted in writing 
                  within exactly <strong>seven (7) calendar days</strong> of their initial subscription tier activation, or the 
                  commencement/renewal date of their recurring monthly billing cycle. 
                </p>
                <p className="mt-2 text-xs text-red-600 font-medium">
                  Important: Any refund request initiated on or after the eighth (8th) day of the cycle shall be systematically rejected.
                </p>
              </div>

              <p>
                This grace window enables factory operators to fully test the database speeds, worker attendance interfaces, and 
                OpenClaw automated reporting structures in a live operational environment with zero permanent financial commitment.
              </p>
            </section>

            {/* Section 2 */}
            <section id="credit-process" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                2. Systematic Crediting &amp; Processing
              </h2>
              <p className="mb-4">
                To guarantee transparency and speed, all approved refund payments are routed systematically through our automated merchant accounts.
              </p>

              <div className="my-6 rounded-xl border-l-4 border-[#6D28D9] bg-[#FFF7ED] p-5 shadow-sm">
                <h4 className="font-bold text-[#111827] mb-2 uppercase tracking-wide text-xs">Standard Crediting Clause</h4>
                <p className="text-xs sm:text-sm text-[#4B5563] leading-relaxed font-semibold">
                  "Approved refund claims initiated within the valid 7-day window will be systematically credited back to the user's original payment source within 7 to 10 working days."
                </p>
              </div>

              <p>
                Depending on your financial institution's processing cycles (including banks, card networks, and local UPI gateways), 
                the refund transaction may take additional business days to appear on your bank statement. Cosmic Yog will issue a transaction 
                completion slip via registered workspace emails immediately upon internal authorization.
              </p>
            </section>

            {/* Section 3 */}
            <section id="cancellation" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                3. B2B Cancellation Guidelines
              </h2>
              <p className="mb-4">
                As a B2B SaaS software built to maintain complex multi-user databases, our subscription cancellation workflow is engineered 
                to avoid sudden shutdowns that could stall physical factory shop floors:
              </p>
              
              <ul className="list-decimal pl-5 space-y-3 mb-4">
                <li>
                  <strong className="text-[#4C1D95]">No Pro-Rated Mid-Cycle Credits:</strong> Cancellations requested after the 7-day 
                  refund window has elapsed will prevent future billing renewals but are completely non-refundable. The subscription remains 
                  active for the remainder of the current paid billing duration.
                </li>
                <li>
                  <strong className="text-[#4C1D95]">Active Access Retention:</strong> To ensure business continuity, your workspace, including 
                  active operator logs, inventory lists, and supervisor sheets, will remain active and usable until the final second of the 
                  active monthly billing cycle.
                </li>
                <li>
                  <strong className="text-[#4C1D95]">Critical Data Export Period:</strong> Factory managers must export all historical ledger logs, 
                  worker profiles, and inventory registers using the CSV/JSON download tools <em>before</em> the billing cycle officially ends. 
                  Once the subscription terminates, workspace access is restricted and databases are queued for scheduled deletion as outlined 
                  in our Privacy Policy.
                </li>
              </ul>
            </section>

            {/* Section 4 */}
            <section id="tier-modifications" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                4. Tier Modifications &amp; Upgrades
              </h2>
              <p className="mb-4">
                When a factory upgrades its active tier mid-cycle (e.g. scaling from the Lite tier to Enterprise to support more workers 
                or integrations), the database immediately adjusts capabilities. 
              </p>
              <p>
                Upgrades will charge a pro-rated difference for the remaining active days of the monthly cycle. Refunds or pro-rated cash-backs 
                are not issued if a factory decides to downgrade its active package mid-month; instead, the downsized limits will take effect 
                commencing from the next monthly billing cycle startup.
              </p>
            </section>

            {/* Section 5 */}
            <section id="ineligible-claims" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                5. Ineligible Refund Claims
              </h2>
              <p className="mb-4">
                To prevent fraud and maintain the integrity of our software services, refunds are explicitly disallowed in the following events:
              </p>
              <ul className="list-disc pl-5 space-y-2 mb-4 text-[#4B5563]">
                <li>Workspace terminations resulting from structural violations of our Terms &amp; Conditions (e.g. credential sharing or attempting to scrape proprietary code).</li>
                <li>Disputes regarding scheduled maintenance downtime or upstream API outages, which are covered under the standard Liability Waiver in our Terms &amp; Conditions.</li>
                <li>Multiple consecutive registrations and refund claims by the same factory owner under alternate names to exploit the 7-day guarantee window.</li>
              </ul>
            </section>

          </div>
        </div>

        {/* Footer print-only watermark */}
        <div className="hidden print:block mt-12 text-center text-xs text-gray-400 border-t pt-4">
          MunshiAI Refund &amp; Cancellation Policy • Cosmic Yog Legal Compliance Department • Printed securely.
        </div>
      </div>
    </div>
  );
}
