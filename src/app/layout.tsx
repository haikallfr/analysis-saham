import type { Metadata } from "next";
import { Plus_Jakarta_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";

const fontSans = Plus_Jakarta_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
});

const fontMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

import ActiveScanOverlay from "@/components/ActiveScanOverlay";

export const metadata: Metadata = {
  title: "ValueScanner Pro - IDX Advanced Analytics",
  description: "Enterprise grade IDX stock screener and valuation tool",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id">
      <body className={`${fontSans.variable} ${fontMono.variable} antialiased font-sans`}>
        <Navbar />
        <main className="max-w-7xl mx-auto px-6 pb-20">
          {children}
        </main>
        <ActiveScanOverlay />
      </body>
    </html>
  );
}
