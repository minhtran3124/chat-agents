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
        cream: "#f9f6ef",
        paper: "#fdfbf5",
        ink: "#1a1816",
        subink: "#5c5956",
        rule: "#d8d3c4",
        terracotta: "#b5491c",
        olive: "#5a6b3e",
        amber: "#b07d1c",
        danger: "#a63b3b",
      },
      fontFamily: {
        display: ["var(--font-fraunces)", "Georgia", "serif"],
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        caps: "0.12em",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
export default config;
