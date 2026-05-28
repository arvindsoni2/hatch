"use client";
import { useState, useEffect } from "react";

export function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<Event | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (localStorage.getItem("pwa-install-dismissed")) {
      setDismissed(true);
      return;
    }
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  if (!deferredPrompt || dismissed) return null;

  return (
    <div className="fixed bottom-20 md:bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 z-50 bg-white border border-slate-200 rounded-xl shadow-lg p-4">
      <p className="font-medium text-sm text-slate-900 mb-1">Install Hatch</p>
      <p className="text-xs text-slate-500 mb-3">Add to your home screen for quick access on any device.</p>
      <div className="flex gap-2">
        <button
          onClick={() => {
            (deferredPrompt as BeforeInstallPromptEvent).prompt();
            setDeferredPrompt(null);
          }}
          className="flex-1 bg-indigo-600 text-white rounded-lg py-2.5 text-sm font-medium min-h-[44px]"
        >
          Install
        </button>
        <button
          onClick={() => {
            setDismissed(true);
            localStorage.setItem("pwa-install-dismissed", "1");
          }}
          className="px-4 text-slate-400 text-sm min-h-[44px]"
        >
          Not now
        </button>
      </div>
    </div>
  );
}

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
}
