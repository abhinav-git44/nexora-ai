import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { Providers } from "./providers";
import { themeInitScript } from "@/lib/theme";

export const metadata: Metadata = {
  title: { default: "NEXORA AI — One Intelligent Workspace", template: "%s · NEXORA AI" },
  description: "AI business operations & workflow intelligence: knowledge, agents, automation and analytics in one workspace.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: [{ media: "(prefers-color-scheme: dark)", color: "#0b0b0f" }, { color: "#fafafa" }] };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeInitScript }} /></head>
      <body className="min-h-screen font-sans antialiased"><Providers>{children}</Providers></body>
    </html>
  );
}
