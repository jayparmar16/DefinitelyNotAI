import type { Metadata } from "next";
import type { ReactNode } from "react";

// Hanken Grotesk, self-hosted (the latin variable-weight woff2), used through --font-sans.
import "@fontsource-variable/hanken-grotesk";
import "./globals.css";

export const metadata: Metadata = {
  title: "AskWRI",
  description: "Answers from World Resources Institute research, with a citation for every claim.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
