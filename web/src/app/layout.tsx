import type { Metadata } from "next";
import { plexMono, plexSans, plexSerif } from "@/lib/fonts";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "WhaleTale",
  description: "Per-space foot-traffic for multi-tenant properties.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${plexSans.variable} ${plexSerif.variable} ${plexMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
