/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        bg2: "var(--bg2)",
        bg3: "var(--bg3)",
        bg4: "var(--bg4)",
        text: "var(--text)",
        text2: "var(--text2)",
        text3: "var(--text3)",
        border: "var(--border)",
        border2: "var(--border2)",
        accent: "var(--accent)",
        accentBg: "var(--accent-bg)",
        accentBorder: "var(--accent-border)",
        green: "var(--green)",
        greenBg: "var(--green-bg)",
        amber: "var(--amber)",
        amberBg: "var(--amber-bg)",
        red: "var(--red)",
      },
      fontFamily: {
        sans: ["'DM Sans'", "sans-serif"],
        mono: ["'DM Mono'", "monospace"],
      },
      borderRadius: {
        card: "8px",
        "card-lg": "12px",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        fadeUp: "fadeUp .35s ease both",
        pulseSoft: "pulseSoft 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
