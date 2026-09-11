
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: { mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"] },
      colors: {
        hud: { cyan: "#22d3ee", amber: "#f59e0b", red: "#ef4444", violet: "#a78bfa", green: "#22c55e" },
      },
      boxShadow: {
        "glow-cyan": "0 0 12px rgba(34,211,238,0.55)",
        "glow-red": "0 0 16px rgba(239,68,68,0.65)",
        "glow-amber": "0 0 12px rgba(245,158,11,0.55)",
      },
      keyframes: {
        pulseRing: { "0%": { transform: "scale(0.8)", opacity: "0.9" }, "100%": { transform: "scale(2.2)", opacity: "0" } },
        scan: { "0%": { transform: "translateY(-100%)" }, "100%": { transform: "translateY(100%)" } },
      },
      animation: { pulseRing: "pulseRing 1.6s ease-out infinite", scan: "scan 4s linear infinite" },
    },
  },
  plugins: [],
};