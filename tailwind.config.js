/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        pal: {
          cream: "#f1dac4",
          mauve: "#a69cac",
          slate: "#474973",
          navy: "#161b33",
          ink: "#0d0c1d",
        },
      },
    },
  },
  plugins: [],
};
