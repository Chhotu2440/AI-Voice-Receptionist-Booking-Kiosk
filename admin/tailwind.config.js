/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
      colors: {
        brand: {
          50: "#f3f1ff",
          100: "#e9e5ff",
          200: "#d5cdff",
          300: "#b6a6ff",
          400: "#9474ff",
          500: "#7a45fb",
          600: "#6c23f3",
          700: "#5d16d7",
          800: "#4e13b4",
          900: "#411293",
        },
      },
    },
  },
  plugins: [],
};
