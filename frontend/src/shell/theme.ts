export type Theme = "light" | "dark";

/** Kept in sync with the script in index.html, which applies it before the first paint. */
export const THEME_KEY = "studio.theme";

/** A saved choice wins; without one the Studio follows the computer. */
export function resolveTheme(saved: string | null, prefersLight: boolean): Theme {
  if (saved === "light" || saved === "dark") return saved;
  return prefersLight ? "light" : "dark";
}

function saved(): string | null {
  try {
    return window.localStorage.getItem(THEME_KEY);
  } catch {
    // Storage can be blocked; the computer's setting still applies.
    return null;
  }
}

function prefersLight(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ?? false;
}

export function currentTheme(): Theme {
  return resolveTheme(saved(), prefersLight());
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export function chooseTheme(theme: Theme) {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage can be blocked; the choice just lasts this visit.
  }
  applyTheme(theme);
}

/** Follow the computer's light or dark setting until the owner picks one here. */
export function followSystemTheme(onChange: (theme: Theme) => void): () => void {
  const query = window.matchMedia?.("(prefers-color-scheme: light)");
  if (!query) return () => undefined;
  const listener = () => {
    if (saved() !== null) return;
    const theme = currentTheme();
    applyTheme(theme);
    onChange(theme);
  };
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
}
