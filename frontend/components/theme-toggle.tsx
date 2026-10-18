"use client";

import { MoonIcon, SunIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/app/theme-runtime";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const label = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";

  return (
    <Button
      variant="outline"
      size="icon"
      aria-label={label}
      title={label}
      aria-pressed={theme === "dark"}
      onClick={toggleTheme}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </Button>
  );
}
