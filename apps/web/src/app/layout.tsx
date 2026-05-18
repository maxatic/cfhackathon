import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SwiftForecast MCP",
  description: "B2B order forecasting exposed through Model Context Protocol.",
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
