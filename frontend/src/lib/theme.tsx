"use client";
import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";
const Ctx = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({ theme: "system", setTheme: () => undefined });

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  useEffect(() => {
    try {
      setThemeState((localStorage.getItem("nx_theme") as Theme) || "system");
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  const setTheme = (t: Theme) => {
    setThemeState(t);
    try { localStorage.setItem("nx_theme", t); } catch { /* ignore */ }
  };
  return <Ctx.Provider value={{ theme, setTheme }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);

export const themeInitScript = `(function(){try{var t=localStorage.getItem('nx_theme')||'system';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.classList.add('dark')}catch(e){}})()`;
