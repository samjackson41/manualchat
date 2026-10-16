import type { Metadata } from "next";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatRuntimeProvider } from "./chat-runtime";
import { VehicleProvider } from "./vehicle-runtime";

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
          <VehicleProvider>
            <ChatRuntimeProvider>{children}</ChatRuntimeProvider>
          </VehicleProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}