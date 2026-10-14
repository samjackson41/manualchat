import type { Metadata } from "next";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatRuntimeProvider } from "./chat-runtime";

export const metadata: Metadata = {
  title: "ManualChat",
  description: "Grounded repair-manual assistant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <TooltipProvider>
          <ChatRuntimeProvider>{children}</ChatRuntimeProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}