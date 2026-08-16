import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The build lands in `splitbill/render/webui/`, which `serve.py` serves and the
// wheel packages. Built output is committed: the alternative is that `pip install
// splitbill && splitbill serve` shows a placeholder unless the user also has node,
// and a tool nobody can run is not a tool. Regenerate with `npm run build`.
export default defineConfig({
  plugins: [vue()],
  base: './',
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: fileURLToPath(new URL('../splitbill/render/webui', import.meta.url)),
    emptyOutDir: true,
    // Inlined assets would be base64 in the JS; keeping them as files means the
    // print stylesheet is a stylesheet, which is easier to check by reading.
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        // ECharts is still the larger half and changes only when it is upgraded.
        // Splitting it keeps the app chunk small enough to read the diff of.
        manualChunks: { echarts: ['echarts/core', 'echarts/charts',
                                  'echarts/components', 'echarts/renderers'] },
      },
    },
  },
  server: {
    port: 5173,
    // `npm run dev` serves the page; the Python service still answers the API.
    // Origin is checked there and localhost:5173 is accepted, so this works
    // without weakening the check.
    proxy: {
      '/api': `http://127.0.0.1:${process.env.SPLITBILL_API_PORT ?? '8765'}`,
    },
  },
})
