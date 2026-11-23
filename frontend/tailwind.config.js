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
          green: '#39FF14', // Electric Neon Green (Primary)
          cyan: '#7DF9FF',  // Electric Cyan (Secondary Accent)
          red: '#CC162D',   // Signal Red (Accents & High Congestion)
        },
        surface: {
          base: '#070A08',     // Deep charcoal with slight green undertone
          card: '#0D140F',     // Translucent smoked glass surface
          cardHover: '#111A14',
          elevated: '#17221A', // Graphite elevated layer
          border: 'rgba(255, 255, 255, 0.08)',
          borderHover: 'rgba(57, 255, 20, 0.3)',
          subtle: '#1C2920',
        },
        text: {
          primary: '#F4F7F5',
          secondary: '#8E9E93',
          muted: '#5A695F',
        }
      },
      fontFamily: {
        display: ['"Geist"', '"Inter"', 'system-ui', 'sans-serif'],
        sans: ['"Geist"', '"Inter"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"Geist Mono"', '"IBM Plex Mono"', 'monospace'],
      },
      boxShadow: {
        'glass-card': '0 8px 32px 0 rgba(0, 0, 0, 0.45), inset 0 1px 0 0 rgba(255, 255, 255, 0.12)',
        'glass-glow': '0 0 25px -4px rgba(57, 255, 20, 0.25), inset 0 1px 1px 0 rgba(255, 255, 255, 0.2)',
        'glass-specular': 'inset 0 1px 1px 0 rgba(255, 255, 255, 0.2), 0 12px 35px -8px rgba(0, 0, 0, 0.55)',
        'glow-green': '0 0 30px -5px rgba(57, 255, 20, 0.4)',
        'glow-cyan': '0 0 25px -5px rgba(125, 249, 255, 0.35)',
        'glow-red': '0 0 25px -5px rgba(204, 22, 45, 0.35)',
      },
      backgroundImage: {
        'radial-ambient': 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(57, 255, 20, 0.12), transparent)',
        'radial-cyan-ambient': 'radial-gradient(ellipse 60% 40% at 80% 10%, rgba(125, 249, 255, 0.08), transparent)',
      }
    },
  },
  plugins: [],
}
