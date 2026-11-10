/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        arena: { 950: "#07080F", 900: "#0B0D18", 800: "#10131F", 700: "#181C2C", 600: "#232842" },
        laser: { DEFAULT: "#22E4FF", dim: "#1592A6" },
        plasma: "#FF2BD6",
        signal: "#B6FF3B",
        alert: "#FFB020",
        ink: { DEFAULT: "#EDEFF7", muted: "#A3A9C2" },
      },
      fontFamily: {
        display: ["Orbitron", "Noto Sans Devanagari", "sans-serif"],
        body: ["Inter", "Noto Sans Devanagari", "sans-serif"],
      },
      boxShadow: {
        laser: "0 0 0 2px rgba(34,228,255,0.9), 0 0 24px rgba(34,228,255,0.35)",
        plasma: "0 0 0 2px rgba(255,43,214,0.9), 0 0 24px rgba(255,43,214,0.35)",
      },
      keyframes: {
        breathe: { "0%,100%": { transform: "scale(1)", opacity: "0.85" }, "50%": { transform: "scale(1.06)", opacity: "1" } },
        sweep: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(100%)" } },
        rise: { "0%": { transform: "translateY(16px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
      },
      animation: {
        breathe: "breathe 3.2s ease-in-out infinite",
        sweep: "sweep 1.6s ease-in-out",
        rise: "rise 260ms ease-out both",
      },
    },
  },
  plugins: [],
};
