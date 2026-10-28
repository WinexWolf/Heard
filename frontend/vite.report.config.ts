import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// The CLI report is one self-contained HTML file (JS and CSS inlined), so it opens from a CI artifact or file://
// with no server. It is written into the Python package, where `heard check` fills in __HEARD_REPORT__.
function inlineAssets(): Plugin {
  return {
    name: 'heard-inline-assets',
    enforce: 'post',
    generateBundle(_, bundle) {
      const html = Object.values(bundle).find(a => a.type === 'asset' && a.fileName.endsWith('.html'))
      if (!html || html.type !== 'asset') return
      let page = String(html.source)
      for (const [name, item] of Object.entries(bundle)) {
        if (item.type === 'chunk') {
          const code = item.code.replace(/<\/script/g, '<\\/script')
          page = page.replace(new RegExp(`<script type="module" crossorigin src="[^"]*${name}"></script>`), () => `<script type="module">${code}</script>`)
          delete bundle[name]
        } else if (name.endsWith('.css')) {
          page = page.replace(new RegExp(`<link rel="stylesheet" crossorigin href="[^"]*${name}">`), () => `<style>${item.source}</style>`)
          delete bundle[name]
        }
      }
      html.source = page
    },
  }
}

export default defineConfig({
  plugins: [react(), inlineAssets()],
  publicDir: false,
  build: {
    outDir: resolve(__dirname, '../heard/app/report_ui'), emptyOutDir: true,
    modulePreload: false, cssCodeSplit: false,
    rollupOptions: { input: resolve(__dirname, 'report.html') },
  },
})
