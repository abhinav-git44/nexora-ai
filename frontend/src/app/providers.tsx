"use client";
import { SWRConfig } from "swr";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";
import { fetcher } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <SWRConfig value={{ fetcher, revalidateOnFocus: false, shouldRetryOnError: false }}>
        <AuthProvider>{children}</AuthProvider>
      </SWRConfig>
      <Toaster position="bottom-right" richColors closeButton />
    </ThemeProvider>
  );
}
