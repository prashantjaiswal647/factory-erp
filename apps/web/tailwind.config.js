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
          50: "#eef8f6",
          100: "#d6eee9",
          500: "#1f9d8a",
          600: "#177f72",
          700: "#12665d"
        }
      }
    }
  },
  plugins: []
};
