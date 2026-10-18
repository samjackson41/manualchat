export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "manualchat:theme";

export function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark";
}

// The visitor's stored choice, or null when they have never picked one.
export function storedTheme(): Theme | null {
  const value = window.localStorage.getItem(THEME_STORAGE_KEY);
  return isTheme(value) ? value : null;
}

// Runs before the first paint, so the page never flashes the wrong theme.
export function themeInitScript(): string {
  const key = JSON.stringify(THEME_STORAGE_KEY);
  return (
    `(function(){try{` +
    `var stored=window.localStorage.getItem(${key});` +
    `var dark=stored?stored==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;` +
    `var root=document.documentElement;` +
    `root.classList.toggle("dark",dark);` +
    `root.style.colorScheme=dark?"dark":"light";` +
    `}catch(error){}})();`
  );
}
