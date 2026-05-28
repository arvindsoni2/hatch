import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Navigation } from "@/components/Navigation";
import { BottomNav } from "@/components/BottomNav";
import { OfflineIndicator } from "@/components/OfflineIndicator";
import { InstallPrompt } from "@/components/InstallPrompt";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "JobPilot — Autonomous Job Search",
  description: "AI-powered autonomous job search automation.",
  keywords: ["contract jobs", "solutions architect", "autonomous job search"],
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
  },
  icons: {
    apple: "/icons/icon-192x192.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="theme-color" content="#4f46e5" />
      </head>
      <body className={`${inter.variable} font-sans antialiased bg-slate-50 text-slate-900`}>
        <OfflineIndicator />
        <Navigation />

        <main className="mx-auto max-w-7xl px-4 py-8 pb-24 sm:px-6 lg:px-8 md:pb-8">
          {children}
        </main>

        <BottomNav />
        <InstallPrompt />

        <footer className="mt-16 border-t border-slate-200 bg-white py-6 hidden md:block">
          <div className="mx-auto max-w-7xl px-4 text-center text-sm text-slate-400 sm:px-6 lg:px-8">
            JobPilot — autonomous job search, human-in-the-loop approvals
          </div>
        </footer>
      </body>
    </html>
  );
}
