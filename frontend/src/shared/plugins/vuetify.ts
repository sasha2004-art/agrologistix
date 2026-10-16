import { createVuetify } from 'vuetify'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

export const vuetify = createVuetify({
  theme: {
    defaultTheme: 'agroDark',
    themes: {
      agroDark: {
        dark: true,
        colors: {
          background: '#0F172A',
          surface: '#1E293B',
          primary: '#10B981',
          secondary: '#38BDF8',
          warning: '#F59E0B',
          error: '#EF4444',
          success: '#22C55E',
        },
      },
    },
  },
  defaults: {
    VBtn: { rounded: 'lg', class: 'text-none' },
  },
})
