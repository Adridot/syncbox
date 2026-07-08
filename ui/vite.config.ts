import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

import pkg from './package.json'

export default defineConfig({
  plugins: [vue()],
  define: {
    // Single-source version (SPEC-UNIFIED 6.11, T13): package.json is the
    // canonical source; tauri.conf.json points at it, the sidecar/shell
    // manifests are pinned to it by sidecar/tests/test_version_single_source.py.
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    port: 5173,
    strictPort: true, // the shell's devUrl and the sidecar CORS regex expect this exact port
  },
  test: {
    environment: 'jsdom',
  },
})
