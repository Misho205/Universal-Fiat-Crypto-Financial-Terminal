import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ThemeProvider } from "../src/components/theme-provider";

export const metadata: Metadata = { title: "HybridPay Terminal", description: "Merchant web/PWA terminal + customer QR checkout" };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="bg" suppressHydrationWarning>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
