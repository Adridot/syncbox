import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    strictPort: true, // the shell's devUrl and the sidecar CORS regex expect this exact port
  },
  test: {
    environment: 'jsdom',
  },
})
