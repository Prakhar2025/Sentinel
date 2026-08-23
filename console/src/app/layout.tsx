import type { Metadata } from "next";
import { Instrument_Serif, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import { CommandBar } from "@/components/CommandBar";
import "./globals.css";

const serif = Instrument_Serif({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-instrument-serif",
});

const sans = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: "Sentinel, Abuse-Ring Watchroom",
  description:
    "Analyst console for Abuse-Ring Sentinel: cross-merchant identity-reuse fraud detection with measured precision, recall, and rupee-denominated false-positive cost.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        <CommandBar />
        <main className="mx-auto max-w-[1440px] px-6 pb-16">{children}</main>
      </body>
    </html>
  );
}
