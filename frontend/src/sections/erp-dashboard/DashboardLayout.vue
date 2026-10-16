<template>
  <v-app-bar height="64" color="surface" class="soft-bar">
    <v-app-bar-title class="text-body-1 font-weight-medium">AgroLogistix</v-app-bar-title>
    <v-chip size="small" variant="tonal" color="primary" class="mr-2 d-none d-sm-flex">
      Калуга — Обнинск
    </v-chip>
    <v-btn variant="text" prepend-icon="mdi-logout" @click="logout">Выйти</v-btn>
  </v-app-bar>

  <v-main>
    <v-container max-width="880" class="py-10">
      <h1 class="text-h5 font-weight-regular mb-2">Рабочее пространство диспетчера</h1>
      <p class="text-body-2 text-medium-emphasis mb-6">
        Здесь появятся склады, заявки, автопарк и карта маршрутов Калужской области.
      </p>
      <v-alert type="info" variant="tonal" icon="mdi-information-outline">
        Модули ERP и маршрутизации подключаются после готовности API (GET /api/v1/erp/state).
      </v-alert>
    </v-container>
  </v-main>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'

const auth = useAuthStore()
const router = useRouter()

function logout(): void {
  auth.logout()
  void router.replace('/login')
}
</script>
