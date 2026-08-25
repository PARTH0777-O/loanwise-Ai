/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12181F",
        paper: "#EFF1ED",
        surface: "#FFFFFF",
        line: "#D8DAD3",
        primary: {
          DEFAULT: "#2C5FA8",
          dark: "#1F4779",
          light: "#E4ECF6",
        },
        risk: {
          low: "#1E7F6E",
          lowBg: "#E3F1EE",
          medium: "#C08A2E",
          mediumBg: "#F6EDDD",
          high: "#B23A2E",
          highBg: "#F6E4E1",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
    },
  },
  plugins: [],
};
