import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#e8f0fe",
          100: "#c3d7fd",
          200: "#90b8fb",
          300: "#5b97f8",
          400: "#3b82f6",
          500: "#1d6af5",
          600: "#1558e0",
          700: "#1047b8",
          800: "#0d3a94",
          900: "#0a2d72",
        },
        navy: {
          900: "#0d1b2a",
          800: "#112235",
          700: "#152b42",
          600: "#1a3451",
          500: "#1e3d60",
        },
        surface: {
          DEFAULT: "#111827",
          raised: "#1f2937",
          border: "#374151",
        },
      },
      fontFamily: {
        sans: ["Inter", "Noto Sans KR", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
