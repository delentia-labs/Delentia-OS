/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Delentia brand colors
        delentia: {
          50:  "hsla(var(--primary), 0.1)",
          100: "hsla(var(--primary), 0.2)",
          500: "hsl(var(--primary))",
          600: "hsl(var(--primary))",
          700: "hsla(var(--primary), 0.8)",
          900: "hsla(var(--primary), 0.2)",
        },
        // Round 50 Desk palette (see globals.css); the three greens are the
        // three layers of the Delentia mark.
        dl: {
          ink: "rgb(var(--dl-ink-rgb) / <alpha-value>)",
          panel: "rgb(var(--dl-panel-rgb) / <alpha-value>)",
          panel2: "rgb(var(--dl-panel-2-rgb) / <alpha-value>)",
          rule: "rgb(var(--dl-rule-rgb) / <alpha-value>)",
          text: "rgb(var(--dl-text-rgb) / <alpha-value>)",
          muted: "rgb(var(--dl-muted-rgb) / <alpha-value>)",
          leaf: "rgb(var(--dl-leaf-rgb) / <alpha-value>)",
          fern: "rgb(var(--dl-fern-rgb) / <alpha-value>)",
          pine: "rgb(var(--dl-pine-rgb) / <alpha-value>)",
          eye: "rgb(var(--dl-eye-rgb) / <alpha-value>)",
          amber: "rgb(var(--dl-amber-rgb) / <alpha-value>)",
          rust: "rgb(var(--dl-rust-rgb) / <alpha-value>)",
        },
        surface: {
          DEFAULT: "hsl(var(--background))",
          card:    "hsl(var(--surface-card))",
          border:  "hsl(var(--surface-border))",
        },
      },
      fontFamily: {
        mono: ["var(--font-plex-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
        thai: ["var(--font-plex-thai)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
  darkMode: "class",
};
