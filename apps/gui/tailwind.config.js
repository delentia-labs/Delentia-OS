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
        surface: {
          DEFAULT: "hsl(var(--background))",
          card:    "hsl(var(--surface-card))",
          border:  "hsl(var(--surface-border))",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
  darkMode: "class",
};
