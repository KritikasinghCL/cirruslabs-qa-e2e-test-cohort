/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        vedanta: {
          red: '#C0392B',
          dark: '#1A1A2E',
          navy: '#16213E',
          blue: '#0F3460',
          accent: '#E94560',
          gold: '#F5A623',
          green: '#27AE60',
          amber: '#F39C12',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      }
    }
  },
  plugins: []
}
