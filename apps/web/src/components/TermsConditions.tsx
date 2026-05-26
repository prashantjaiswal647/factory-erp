import React, { useState } from "react";

export default function TermsConditions() {
  const [activeSection, setActiveSection] = useState("agreement");

  const sections = [
    { id: "agreement", title: "1. Scope & Binding Agreement" },
    { id: "account-ownership", title: "2. Authentication Security & Liability" },
    { id: "liability-waiver", title: "3. Service Downtime Limitation" },
    { id: "human-loop", title: "4. Human-In-The-Loop Verification" },
    { id: "governing-law", title: "5. Governing Law & Dispute Resolution" },
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
              Print Terms
            </button>
            <a
              href="mailto:cosmicyog7@gmail.com?subject=MunshiAI%20Terms%20Inquiry"
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
                incorporated business or factory (referred to as the "User", "Licensee", or "you"), and 
                <strong> Cosmic Yog</strong> ("Company", "we", "us", or "our"), under the sole proprietorship of <strong>PRASHANT</strong>, 
                with its registered office located at <strong>K46/189 hartirath varanasi 221001, VARANASI, 221001, Uttar Pradesh</strong>, concerning 
                your access to and use of the <strong>MunshiAI</strong> software application.
              </p>
            </section>

            {/* Section 2 */}
            <section id="account-ownership" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                2. Authentication Security &amp; Liability
              </h2>
              <p className="mb-4">
                Our secure login environment utilizes Phone Number authentication coupled with password credentials. The registered <strong>Factory Manager</strong> or administrator is <strong>solely responsible</strong> for safeguarding password hashes, restricting local employee credentials, and maintaining the confidentiality of operational session keys.
              </p>
              <p>
                Cosmic Yog shall hold zero liability for data losses, unauthorized alterations, or security exposures resulting from credential sharing, local operational negligence, or mobile device compromise.
              </p>
            </section>

            {/* Section 3 */}
            <section id="liability-waiver" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                3. Service Downtime Limitation
              </h2>
              <div className="my-6 rounded-xl border-l-4 border-amber-500 bg-amber-50 p-5 shadow-sm">
                <h4 className="font-bold text-[#111827] mb-2 uppercase tracking-wide text-xs text-amber-800">
                  IMPORTANT LEGAL NOTICE: Liability &amp; Downtime Waiver
                </h4>
                <p className="text-xs sm:text-sm text-amber-900 leading-relaxed font-semibold">
                  "Cosmic Yog or MunshiAI holds zero financial liability for any direct, indirect, or consequential manufacturing pauses, production losses, factory output drops, staff idle-time payroll costs, or sync delays arising from scheduled maintenance, network dropouts, upstream hosting outages, or third-party server downtime."
                </p>
              </div>
            </section>

            {/* Section 4 */}
            <section id="human-loop" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                4. Human-In-The-Loop Verification
              </h2>
              <p className="mb-4">
                All production metrics, monthly sheet calculations, automated raw material yields, and estimated wastage computations processed via the OpenClaw AI engine or automated pipeline utilities serve as supportive planning metrics only.
              </p>
              <p className="font-semibold text-[#111827]">
                The Factory Administrator must verification-check and manually sign off on all automated sheets and wastage reports before utilizing them for payroll, regulatory invoicing, tax filings, or commercial business decisions.
              </p>
            </section>

            {/* Section 5 */}
            <section id="governing-law" className="scroll-mt-6">
              <h2 className="text-xl font-bold text-[#4C1D95] border-b border-[#F5E6D3] pb-2 mb-3">
                5. Governing Law &amp; Support Contact
              </h2>
              <p className="mb-4">
                These terms shall be governed by and construed in accordance with the laws of Uttar Pradesh, India. Any dispute arising out of this contract shall be settled under the exclusive jurisdiction of the courts of Varanasi, Uttar Pradesh, India.
              </p>
              <div className="rounded-xl bg-[#FFF7ED] p-5 border border-[#F5E6D3] text-xs sm:text-sm">
                <p className="font-bold text-[#4C1D95]">Cosmic Yog Support Desk</p>
                <p>Proprietor: PRASHANT</p>
                <p>Office Address: K46/189 hartirath varanasi 221001, VARANASI, 221001, Uttar Pradesh</p>
                <p>Email: <a href="mailto:cosmicyog7@gmail.com" className="text-[#6D28D9] hover:underline">cosmicyog7@gmail.com</a></p>
                <p>Phone Support: <span className="font-semibold text-[#111827]">8285811727</span></p>
              </div>
            </section>

          </div>
        </div>
      </div>
    </div>
  );
}
