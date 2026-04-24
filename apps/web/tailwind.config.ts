import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Surfaces — a true-white canvas with two cool off-white tints.
        canvas: "#ffffff",
        surface: "#f7f8fa",
        "surface-2": "#eef0f3",

        // Rule lines — one neutral, one even softer for in-section divides.
        hairline: "#e5e7eb",
        "hairline-soft": "#eff1f4",

        // Text ladder — charcoal, slate, quiet-slate.
        ink: "#1f2328",
        "ink-muted": "#656d76",
        "ink-dim": "#8c959f",

        // Single dominant accent (teal) + its two siblings.
        accent: "#0891b2",
        "accent-soft": "#06b6d4",
        "accent-deep": "#0e7490",

        // Semantic state colors — used sparingly.
        success: "#16a34a",
        warn: "#d97706",
        danger: "#dc2626",
      },
      fontFamily: {
        display: ["var(--font-fraunces)", "Georgia", "serif"],
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        caps: "0.12em",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(16,24,40,0.04)",
        focus: "0 0 0 3px rgba(8,145,178,0.15)",
        toast: "0 10px 30px -12px rgba(16,24,40,0.12), 0 2px 6px -1px rgba(16,24,40,0.06)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
export default config;
