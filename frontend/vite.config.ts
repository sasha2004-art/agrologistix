import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { fileURLToPath, URL } from 'node:url'

const apiProxy = {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // mapbox-gl и Vuetify — самые тяжёлые зависимости (в одном чанке
        // дашборда они давали 2 МБ). Отдельные чанки грузятся параллельно
        // и переиспользуются из кэша после деплоя, когда меняется только код UI.
        manualChunks(id: string): string | undefined {
          if (id.includes('node_modules/mapbox-gl') || id.includes('node_modules/@mapbox/')) {
            return 'mapbox'
          }
          if (id.includes('node_modules/vuetify')) return 'vuetify'
          return undefined
        },
      },
    },
  },
  server: {
    proxy: apiProxy,
  },
  // `vite preview` отдаёт собранный dist и не наследует server.proxy,
  // без этого /api/* на предпросмотре отвечает 404 и данные не грузятся.
  preview: {
    proxy: apiProxy,
  },
})
