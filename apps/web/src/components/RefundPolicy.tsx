import React, { useState } from "react";

export default function RefundPolicy() {
  const [activeSection, setActiveSection] = useState("refund-window");

  const sections = [
    { id: "refund-window", title: "1. Strict 7-Day Refund window" },
    { id: "credit-process", title: "2. Payout Processing Timeline" },
    { id: "cancellation", title: "3. Post-Threshold Cancellations" },
    { id: "support", title: "4. Contact Support Desk" },
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
              href="mailto:cosmicyog7@gmail.com?subject=MunshiAI%20Refund%20Claim"
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
                1. Strict 7-Day Refund Window
              </h2>
              <p className="mb-4">
                Subscribing enterprise managers of MunshiAI are eligible to claim a full refund of their paid tier fee if requested in writing within exactly <strong>seven (7) calendar days</strong> of their initial subscription tier activation, or the monthly billing cycle renewal date.
              </p>
              <p className="text-xs text-red-600 font-semibold uppercase tracking-wider">
                Any refund request initiated on or after the eighth (8th) day of the cycle is strictly non-eligible and will be rejected.
              </p>
            </section>

            {/* Section 2 */}
            <section id="credit-process" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                2. Payout Processing Timeline
              </h2>
              <div className="my-6 rounded-xl border-l-4 border-[#6D28D9] bg-[#FFF7ED] p-5 shadow-sm">
                <h4 className="font-bold text-[#111827] mb-2 uppercase tracking-wide text-xs">Standard Crediting Clause</h4>
                <p className="text-xs sm:text-sm text-[#4B5563] leading-relaxed font-semibold">
                  "Approved refund claims initiated within the valid 7-day window will be systematically credited back to the user's original payment source within 7 to 10 working days."
                </p>
              </div>
            </section>

            {/* Section 3 */}
            <section id="cancellation" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                3. Post-Threshold Cancellations
              </h2>
              <p className="mb-4">
                Cancellation requests received after the 7-day threshold has elapsed are completely non-refundable for the active billing cycle.
              </p>
              <p>
                Upon post-threshold cancellation, the subscription remains fully active and your factory operator workspaces usable until the final second of the current billing cycle. This stops future recurring billing runs while preventing sudden factory operations halt, allowing sufficient time for database backups and registry exports.
              </p>
            </section>

            {/* Section 4 */}
            <section id="support" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                4. Contact Support Desk
              </h2>
              <p className="mb-4">
                To submit an eligibility refund claim, please contact the Billing &amp; Invoicing desk with your transaction receipt details:
              </p>
              <div className="rounded-xl bg-[#FFF7ED] p-5 border border-[#F5E6D3] text-xs sm:text-sm">
                <p className="font-bold text-[#4C1D95]">Cosmic Yog Billing Desk</p>
                <p>Proprietor: PRASHANT</p>
                <p>Registered Address: K46/189 hartirath varanasi 221001, VARANASI, 221001, Uttar Pradesh</p>
                <p>Email Support: <a href="mailto:cosmicyog7@gmail.com" className="text-[#6D28D9] hover:underline">cosmicyog7@gmail.com</a></p>
                <p>Phone Helpdesk: <span className="font-semibold text-[#111827]">8285811727</span></p>
              </div>
            </section>

          </div>
        </div>
      </div>
    </div>
  );
}
