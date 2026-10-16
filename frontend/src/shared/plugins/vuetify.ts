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
          'surface-variant': '#F7F5F0',
          'surface-light': '#FCFAF6',
          'on-background': '#2B2A26',
          'on-surface': '#2B2A26',
          'on-surface-variant': '#6B675C',
          primary: '#D9B36C',
          'primary-lighten-1': '#E6C88A',
          'primary-darken-1': '#A8842F',
          secondary: '#8CBEDC',
          'secondary-lighten-1': '#A8CFE4',
          'secondary-darken-1': '#5E93B5',
          success: '#7C9A6B',
          'success-lighten-1': '#93AE84',
          warning: '#C9A227',
          'warning-lighten-1': '#D9B85A',
          error: '#B4553F',
          'error-lighten-1': '#C56F5C',
          info: '#8CBEDC',
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
  },
})
