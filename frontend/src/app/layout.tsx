import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { HatchNavShell } from "@/components/hatch/HatchNavShell";
import { HatchTopBarSlot } from "@/components/hatch/HatchTopBarSlot";
import { OfflineIndicator } from "@/components/OfflineIndicator";
import { InstallPrompt } from "@/components/InstallPrompt";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Hatch — AI-powered job search",
  description: "AI-powered autonomous job search with human-in-the-loop approvals.",
  keywords: ["job search", "AI jobs", "autonomous job search", "job discovery"],
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
        <meta name="theme-color" content="#36c5a8" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var stored = localStorage.getItem('theme');
                  var theme = stored === 'light' ? 'light' : 'dark';
                  document.documentElement.setAttribute('data-theme', theme);
                  if (theme === 'dark') document.documentElement.classList.add('dark');
                } catch(e) {
                  document.documentElement.setAttribute('data-theme', 'dark');
                  document.documentElement.classList.add('dark');
                }
              })();
            `,
          }}
        />
      </head>
      <body
        className={`${inter.variable} font-sans antialiased`}
        style={{ background: "var(--bg)", color: "var(--text)" }}
      >
        <OfflineIndicator />

        <div className="flex" style={{ minHeight: "100vh" }}>
          {/* Desktop sidebar (hidden on mobile) — rendered via client shell for pathname awareness */}
          <HatchNavShell />

          {/* Main content area */}
          <div className="flex flex-col flex-1 min-w-0">
            <HatchTopBarSlot />
            <main className="flex-1 px-4 py-6 pb-24 md:px-8 md:py-6 md:pb-8">
              {children}
            </main>
          </div>
        </div>

        <InstallPrompt />
      </body>
    </html>
  );
}
