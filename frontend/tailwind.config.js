/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        neon: {
          green: '#39F58A',
          blue: '#20C8FF',
          maroon: '#761D43',
        },
        surface: {
          base: '#0B0F17',
          card: '#121824',
          elevated: '#1A2234',
          border: '#232E44',
          subtle: '#2E3D5B',
        },
        slate: {
          950: '#07090E',
        }
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        sans: ['"Inter"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', '"JetBrains Mono"', 'monospace'],
      },
      boxShadow: {
        'glow-green': '0 0 25px -5px rgba(57, 245, 138, 0.25)',
        'glow-blue': '0 0 25px -5px rgba(32, 200, 255, 0.25)',
      }
    },
  },
  plugins: [],
}
