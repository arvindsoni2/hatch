"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,       // 30 s — data stays fresh; prevents over-fetching
            gcTime: 5 * 60_000,      // 5 min — keep in cache after unmount
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
