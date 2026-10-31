import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "HybridPay Terminal", description: "Merchant web/PWA terminal + customer QR checkout" };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="bg">
      <body>{children}</body>
    </html>
  );
}
