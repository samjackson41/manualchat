import type { Metadata } from "next";
import "./globals.css";
import { themeInitScript } from "@/lib/theme";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatRuntimeProvider } from "./chat-runtime";
import { ThemeProvider } from "./theme-runtime";
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
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript() }} />
      </head>
      <body>
        <ThemeProvider>
          <TooltipProvider>
            <VehicleProvider>
              <ChatRuntimeProvider>{children}</ChatRuntimeProvider>
            </VehicleProvider>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}