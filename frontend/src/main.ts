import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { vuetify } from './shared/plugins/vuetify'
import './shared/styles/base.scss'
import './shared/styles/excel-table.scss'
import './shared/styles/map.scss'
import './shared/styles/print.scss'

createApp(App).use(createPinia()).use(router).use(vuetify).mount('#app')
