import { createVuetify } from 'vuetify'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

export const vuetify = createVuetify({
  theme: {
    defaultTheme: 'agroLight',
    themes: {
      agroLight: {
        dark: false,
        colors: {
          background: '#FFFFFF',
          surface: '#FFFFFF',
          'surface-variant': '#F5F3EE',
          'on-background': '#2B2A26',
          'on-surface': '#2B2A26',
          'on-surface-variant': '#5B584F',
          primary: '#D9B36C',
          'primary-darken-1': '#A8842F',
          secondary: '#8CBEDC',
          'secondary-darken-1': '#5E93B5',
          success: '#7C9A6B',
          warning: '#C9A227',
          error: '#B4553F',
          info: '#8CBEDC',
        },
      },
    },
  },
  defaults: {
    VBtn: { rounded: 'lg', class: 'text-none' },
  },
})
