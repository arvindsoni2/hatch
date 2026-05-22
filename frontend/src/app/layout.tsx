import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "JobPilot — Contract Job Scout",
  description:
    "AI-powered job application automation for UK outside-IR35 contract roles.",
  keywords: ["contract jobs", "outside IR35", "solutions architect", "UK contracts"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased bg-slate-50 text-slate-900`}>
        {/* Navigation */}
        <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
            <a href="/" className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
                <span className="text-sm font-bold text-white">JP</span>
              </div>
              <span className="text-lg font-semibold text-slate-900">JobPilot</span>
              <span className="hidden rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700 sm:block">
                Scout · Tracker · Tailor · Coach · Agents
              </span>
            </a>
            <nav className="flex items-center gap-6 text-sm font-medium text-slate-600">
              <a href="/" className="hover:text-brand-600 transition-colors">
                Dashboard
              </a>
              <a href="/jobs" className="hover:text-brand-600 transition-colors">
                All Jobs
              </a>
              <a href="/applications" className="hover:text-brand-600 transition-colors">
                Applications
              </a>
              <a href="/auto-apply" className="hover:text-brand-600 transition-colors">
                Auto Apply
              </a>
              <a href="/analytics" className="hover:text-brand-600 transition-colors">
                Analytics
              </a>
              <a href="/calendar" className="hover:text-brand-600 transition-colors">
                Calendar
              </a>
              <a href="/tailor" className="hover:text-brand-600 transition-colors font-semibold text-brand-600">
                Tailor
              </a>
              <a href="/coach" className="hover:text-brand-600 transition-colors font-semibold text-brand-600">
                Coach
              </a>
              <a href="/agents" className="hover:text-brand-600 transition-colors font-semibold text-brand-600">
                Agents
              </a>
              <a href="/approvals" className="hover:text-amber-600 transition-colors font-semibold text-amber-600">
                Approvals
              </a>
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-brand-600 transition-colors"
              >
                API Docs
              </a>
            </nav>
          </div>
        </header>

        {/* Main content */}
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          {children}
        </main>

        {/* Footer */}
        <footer className="mt-16 border-t border-slate-200 bg-white py-6">
          <div className="mx-auto max-w-7xl px-4 text-center text-sm text-slate-400 sm:px-6 lg:px-8">
            JobPilot — Scout · Tracker · Tailor · Coach · Personal tool for UK contract role hunting
          </div>
        </footer>
      </body>
    </html>
  );
}
