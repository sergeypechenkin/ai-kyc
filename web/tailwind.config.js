/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'zava-purple': '#5C2D91',
        'zava-purple-dark': '#4A2275',
        'zava-purple-light': '#7B4FA8',
      },
    },
  },
  plugins: [],
}
