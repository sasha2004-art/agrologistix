<template>
  <main class="dashboard-placeholder">
    <header><RouterLink to="/" class="brand"><v-icon icon="mdi-leaf" /> AgroLogistix</RouterLink><v-btn variant="text" prepend-icon="mdi-logout" @click="logout">Выйти</v-btn></header>
    <section>
      <span class="eyebrow">КАЛУГА · ОБНИНСК</span>
      <h1>Терминал логиста</h1>
      <p>Рабочее пространство диспетчера готовится к подключению.</p>
      <div class="placeholder-state"><v-icon icon="mdi-map-clock-outline" size="25" /><span>Модуль маршрутизации будет доступен после подключения ERP.</span></div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'

const auth = useAuthStore()
const router = useRouter()
function logout(): void {
  auth.logout()
  void router.replace('/login')
}
</script>

<style scoped lang="scss">
.dashboard-placeholder { min-height: 100vh; background: #0f172a; color: #f8fafc; }
header { height: 56px; display: flex; align-items: center; justify-content: space-between; padding: 0 26px; border-bottom: 1px solid rgba(226,232,240,.12); background: #1e293b; }
.brand { display: inline-flex; align-items: center; gap: 9px; color: #f8fafc; text-decoration: none; font-weight: 600; }.brand .v-icon { color: #10b981; }
section { max-width: 820px; margin: 12vh auto; padding: 0 28px; }.eyebrow { color: #6ee7b7; font: 10px var(--font-mono); letter-spacing: .12em; }
h1 { margin: 14px 0 8px; font-size: 36px; font-weight: 500; }section > p { margin: 0; color: #bdc9d8; }
.placeholder-state { display: flex; align-items: center; gap: 14px; margin-top: 38px; padding: 20px 0; border-top: 1px solid rgba(226,232,240,.12); color: #cbd5e1; font-size: 14px; }.placeholder-state .v-icon { color: #38bdf8; }
</style>
