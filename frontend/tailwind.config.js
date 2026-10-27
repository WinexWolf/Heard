export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: { colors: { ink: '#14171f', accent: { DEFAULT: '#4338ca', dark: '#312e81', soft: '#eef2ff' } },
    fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'], mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'] } } },
  plugins: [],
}
