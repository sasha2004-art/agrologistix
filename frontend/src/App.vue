<template>
  <v-app>
    <RouterView />
    <NotificationHost />
    <PrintableRouteSheet />
  </v-app>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'
import NotificationHost from '@/shared/components/NotificationHost.vue'
import PrintableRouteSheet from '@/sections/erp-dashboard/PrintableRouteSheet.vue'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import { setUnauthorizedHandler } from '@/shared/api/httpClient'
import router from '@/router'

const auth = useAuthStore()

// Ключ отозвали или заменили на сервере: любой ответ 401 возвращает на вход,
// чтобы дашборд не оставался открытым с недействительным ключом.
setUnauthorizedHandler(() => {
  if (!auth.isAuthenticated) return
  auth.logout()
  void router.replace({ name: 'login' })
})
</script>
