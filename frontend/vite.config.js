import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 6173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9010',
        changeOrigin: true,
      },
    },
  },
})
