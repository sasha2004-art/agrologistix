<template>
  <!-- Панель и карта зафиксированы: меню не сворачивается и не тянется мышью. -->
  <v-app-bar height="64" color="surface" class="soft-bar">
    <v-app-bar-title class="text-body-1">
      <span class="brand">AgroLogistix</span>
    </v-app-bar-title>

    <v-spacer />

    <WeatherControlBar class="me-2" />

    <v-btn variant="text" :loading="erp.isLoading" aria-label="Обновить данные" @click="reload">
      <v-icon icon="mdi-refresh" />
      <v-tooltip activator="parent" location="bottom">Обновить данные</v-tooltip>
    </v-btn>
    <v-btn variant="text" prepend-icon="mdi-logout" @click="logout">Выйти</v-btn>
  </v-app-bar>

  <v-navigation-drawer permanent :width="drawerWidth" class="dash-drawer">
    <div class="drawer-body">
      <header class="drawer-head">
        <h1 class="drawer-title">Планирование поставок</h1>
      </header>

      <v-tabs v-model="tab" density="comfortable" show-arrows class="dash-tabs">
        <v-tab value="erp">Заказы</v-tab>
        <v-tab value="fleet">Машины и склады</v-tab>
        <v-tab value="routes">Расчёт</v-tab>
      </v-tabs>

      <v-window v-model="tab" class="dash-window">
        <v-window-item value="erp">
          <div class="tab-scroll"><ClientsOrdersTab /></div>
        </v-window-item>
        <v-window-item value="fleet">
          <div class="tab-scroll">
            <FleetTrucksTab />
            <v-divider class="my-4" />
            <WarehousesStockTab />
          </div>
        </v-window-item>
        <v-window-item value="routes">
          <div class="tab-scroll"><RoutesTcoTab /></div>
        </v-window-item>
      </v-window>
    </div>
  </v-navigation-drawer>

  <v-main class="dash-main">
    <KalugaMapCanvas :routes="solver.routes" />
  </v-main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import ClientsOrdersTab from './ClientsOrdersTab.vue'
import FleetTrucksTab from './FleetTrucksTab.vue'
import KalugaMapCanvas from '@/sections/map-routing/KalugaMapCanvas.vue'
import WeatherControlBar from './WeatherControlBar.vue'
import RoutesTcoTab from './RoutesTcoTab.vue'
import WarehousesStockTab from './WarehousesStockTab.vue'
import { useAssignmentStore } from './useAssignmentStore'
import { useErpStore } from './useErpStore'
import { useSolverStore } from './useSolverStore'

const auth = useAuthStore()
const erp = useErpStore()
const solver = useSolverStore()
const assignments = useAssignmentStore()
const router = useRouter()

/**
 * Рабочее пространство делится 3:2 — три части таблицам, две карте.
 * Соотношение фиксировано: его нельзя перетащить, оно лишь следует за окном.
 */
const PANEL_RATIO = 3 / 5

const viewportWidth = ref(window.innerWidth)
const drawerWidth = computed(() => Math.round(viewportWidth.value * PANEL_RATIO))
const tab = ref('erp')

function syncViewportWidth(): void {
  viewportWidth.value = window.innerWidth
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncViewportWidth)
  erp.stopAutoSync()
})

onMounted(() => {
  window.addEventListener('resize', syncViewportWidth)
  void erp.loadState()
  // Раз в секунду подтягиваем состояние с сервера: store — единственный источник правды.
  erp.startAutoSync()
})

function reload(): void {
  void erp.loadState({ force: true })
}

function logout(): void {
  solver.clear()
  assignments.clear()
  auth.logout()
  void router.replace('/login')
}
</script>

<style scoped lang="scss">
.brand {
  font-family: var(--font-heading);
  font-weight: 600;
}

.dash-drawer {
  border-right: var(--neu-border) !important;
  background: var(--neu-bg) !important;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 18px 24px 12px 18px;
}

.drawer-head {
  margin-bottom: 12px;
}

.drawer-title {
  margin: 0;
  font-size: 18px;
}

.dash-tabs {
  border-bottom: var(--neu-border);
  margin-bottom: 12px;
}

.dash-window {
  flex: 1;
  min-height: 0;
}

.tab-scroll {
  height: 100%;
  max-height: calc(100vh - 220px);
  overflow-x: hidden;
  overflow-y: auto;
  padding: 2px 6px 12px 2px;
}

.dash-window :deep(.v-window-item) {
  min-width: 0;
  max-width: 100%;
}

/* Карта занимает всё доступное место и подстраивается под ширину панели и окно.
   Padding складывается со служебными отступами layout (--v-layout-*): shorthand `padding`
   их затирал, из-за чего карта уезжала под app-bar и под левую панель. */
.dash-main {
  display: flex;
  min-width: 0;
  min-height: 0;
  padding: calc(18px + var(--v-layout-top, 0px)) calc(18px + var(--v-layout-right, 0px))
    calc(18px + var(--v-layout-bottom, 0px)) calc(18px + var(--v-layout-left, 0px));
  overflow: hidden;
}

@media (max-width: 959px) {
  .dash-main {
    padding: calc(12px + var(--v-layout-top, 0px)) calc(12px + var(--v-layout-right, 0px))
      calc(12px + var(--v-layout-bottom, 0px)) calc(12px + var(--v-layout-left, 0px));
  }

  .tab-scroll {
    max-height: none;
  }
}
</style>
