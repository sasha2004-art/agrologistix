import { createVuetify } from 'vuetify'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

export const vuetify = createVuetify({
  theme: {
    defaultTheme: 'serenityLight',
    themes: {
      serenityLight: {
        dark: false,
        colors: {
          background: '#F2ECFB',
          surface: '#F2ECFB',
          'surface-variant': '#E7DFF6',
          'surface-light': '#F7F3FD',
          'on-background': '#2E1065',
          'on-surface': '#2E1065',
          'on-surface-variant': '#5B5175',
          primary: '#6D28D9',
          'primary-lighten-1': '#A78BFA',
          'primary-darken-1': '#5B21B6',
          secondary: '#C4B5FD',
          'secondary-lighten-1': '#DDD6FE',
          'secondary-darken-1': '#5F4BB6',
          accent: '#047857',
          success: '#047857',
          'success-lighten-1': '#34A98B',
          warning: '#B45309',
          'warning-lighten-1': '#D97706',
          error: '#B91C1C',
          'error-lighten-1': '#DC2626',
          info: '#0E7490',
        },
      },
    },
  },
  defaults: {
    VBtn: { rounded: 'lg', class: 'text-none' },
    VCard: { rounded: 'xl', elevation: 0 },
    VAppBar: { flat: true },
    VAlert: { rounded: 'lg' },
    VChip: { rounded: 'lg' },
    VAvatar: { rounded: 'lg' },
    VDialog: { maxWidth: 520 },
  },
})
