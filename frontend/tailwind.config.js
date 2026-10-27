// Design tokens. The scales below replace Tailwind's defaults, so only these values exist as classes.
const px = n => `${n}px`
const hue = (fill, text) => ({ DEFAULT: fill, text })

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    colors: {
      transparent: 'transparent', current: 'currentColor', white: '#ffffff', black: '#000000',
      ink: '#1d1d1f', muted: '#6e6e73', bg: '#f5f5f7', card: '#ffffff',
      accent: { DEFAULT: '#007aff', text: '#0066cc', strong: '#0058b0' },
      blue: hue('#007aff', '#0066cc'), indigo: hue('#5856d6', '#5856d6'), purple: hue('#af52de', '#8944ab'),
      pink: hue('#ff2d55', '#d30f45'), orange: hue('#ff9500', '#c93400'), teal: hue('#30b0c7', '#0071a4'),
      green: hue('#34c759', '#1e7b34'), red: hue('#ff3b30', '#d70015'),
      success: hue('#34c759', '#1e7b34'), destructive: hue('#ff3b30', '#d70015'), warning: hue('#ff9500', '#c93400'),
    },
    spacing: { 0: '0', px: '1px', 1: px(8), 1.5: px(12), 2: px(16), 2.5: px(20), 3: px(24), 4: px(32), 6: px(48), 8: px(64) },
    borderRadius: { none: '0', sm: px(8), md: px(12), lg: px(16), xl: px(24), full: '9999px' },
    boxShadow: { none: 'none', DEFAULT: '0 4px 8px rgb(0 0 0 / 0.08)', glass: '0 8px 32px rgb(0 0 0 / 0.08), inset 0 1px 0 rgb(255 255 255 / 0.6)' },
    fontSize: {
      largeTitle: [px(34), { lineHeight: px(41), fontWeight: '700' }],
      title: [px(28), { lineHeight: px(34), fontWeight: '700' }],
      title2: [px(22), { lineHeight: px(28), fontWeight: '700' }],
      title3: [px(20), { lineHeight: px(25), fontWeight: '600' }],
      headline: [px(17), { lineHeight: px(22), fontWeight: '600' }],
      body: [px(17), px(22)],
      callout: [px(16), px(21)],
      subheadline: [px(15), px(20)],
      footnote: [px(13), px(18)],
      caption: [px(12), px(16)],
      caption2: [px(11), px(13)],
    },
    fontFamily: {
      sans: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
      mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
    },
    extend: {
      borderColor: { DEFAULT: 'rgb(0 0 0 / 0.08)' },
      ringColor: { DEFAULT: '#007aff' },
      minHeight: { tap: px(48) },
      minWidth: { table: px(640) },
      maxWidth: { page: px(1400) },
    },
  },
  plugins: [],
}
