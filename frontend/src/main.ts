import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { vuetify } from './shared/plugins/vuetify'
import './shared/styles/liquid-glass.scss'

createApp(App).use(createPinia()).use(router).use(vuetify).mount('#app')
