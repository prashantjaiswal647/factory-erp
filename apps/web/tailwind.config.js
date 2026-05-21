/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      colors: {
        brand: {
          50: "#F3E8FF",
          100: "#E9D5FF",
          500: "#7C3AED",
          600: "#6D28D9",
          700: "#4C1D95"
        }
      }
    }
  },
  plugins: []
};
