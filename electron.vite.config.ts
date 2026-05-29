import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: {
          main: resolve(__dirname, "electron/main.ts")
        }
      }
    }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: {
          preload: resolve(__dirname, "electron/preload.ts")
        }
      }
    }
  },
  renderer: {
    root: ".",
    plugins: [vue(), tailwindcss()],
    build: {
      rollupOptions: {
        input: resolve(__dirname, "index.html")
      }
    }
  }
});
