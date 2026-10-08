import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinSight — Market Intelligence",
  description: "Financial news intelligence and market-reaction research.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
