export const metadata = { title: "HybridPay Terminal", description: "Merchant web/PWA terminal + customer QR checkout" };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="bg">
      <body>{children}</body>
    </html>
  );
}
