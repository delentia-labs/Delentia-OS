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
          50:  "#f0f4ff",
          100: "#e0eaff",
          500: "#3b6fe8",
          600: "#2d5cd4",
          700: "#1e4abf",
          900: "#0d1f5c",
        },
        surface: {
          DEFAULT: "#0f1117",
          card:    "#1a1d27",
          border:  "#2a2d3e",
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
