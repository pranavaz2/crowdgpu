/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        brand: {
          50:  '#f0f4ff',
          100: '#dce6ff',
          200: '#b9ccff',
          300: '#8aabff',
          400: '#567eff',
          500: '#2d52ff',
          600: '#1530f5',
          700: '#101fdc',
          800: '#121db2',
          900: '#141f8c',
          950: '#0b1157',
        },
      },
    },
  },
  plugins: [],
}
