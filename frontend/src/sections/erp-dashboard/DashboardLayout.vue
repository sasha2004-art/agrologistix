<template>
  <v-app-bar height="64" color="surface" class="soft-bar">
    <v-app-bar-nav-icon
      :icon="drawer ? 'mdi-menu-open' : 'mdi-menu'"
      :aria-label="drawer ? 'Скрыть левое меню' : 'Показать левое меню'"
      :aria-expanded="drawer"
      @click="drawer = !drawer"
    />
    <v-app-bar-title class="text-body-1">
      <span class="brand">Serenity</span>
    </v-app-bar-title>

    <v-spacer />

    <WeatherControlBar class="me-2" />

    <v-btn
      variant="text"
      :loading="erp.isLoading"
      aria-label="Обновить состояние ERP"
      @click="reload"
    >
      <v-icon icon="mdi-refresh" />
      <v-tooltip activator="parent" location="bottom">Обновить состояние</v-tooltip>
    </v-btn>
    <v-btn variant="text" prepend-icon="mdi-logout" @click="logout">Выйти</v-btn>
  </v-app-bar>

  <v-navigation-drawer
    v-model="drawer"
    :permanent="mdAndUp"
    :temporary="!mdAndUp"
    :width="drawerWidth"
    class="dash-drawer"
  >
    <div class="drawer-body">
      <header class="drawer-head">
        <h1 class="drawer-title">Рабочее пространство диспетчера</h1>
        <p class="drawer-subtitle">Состояние загружено: {{ loadedAtText }}</p>
      </header>

      <v-tabs v-model="tab" density="comfortable" show-arrows class="dash-tabs">
        <v-tab value="erp">Склады и заявки</v-tab>
        <v-tab value="fleet">Автопарк</v-tab>
        <v-tab value="routes">Маршруты и TCO</v-tab>
      </v-tabs>

      <v-window v-model="tab" class="dash-window">
        <v-window-item value="erp">
          <div class="tab-scroll">
            <WarehousesStockTab />
            <v-divider class="my-4" />
            <ClientsOrdersTab />
          </div>
        </v-window-item>
        <v-window-item value="fleet">
          <div class="tab-scroll"><FleetTrucksTab /></div>
        </v-window-item>
        <v-window-item value="routes">
          <div class="tab-scroll"><RoutesTcoTab /></div>
        </v-window-item>
      </v-window>
    </div>

    <button
      v-if="mdAndUp"
      type="button"
      class="drawer-resizer"
      :class="{ 'drawer-resizer--active': isResizing }"
      aria-label="Изменить ширину левой панели"
      @pointerdown="startResize"
      @keydown.left.prevent="nudgeDrawer(-40)"
      @keydown.right.prevent="nudgeDrawer(40)"
    >
      <v-icon icon="mdi-drag-vertical" size="16" />
    </button>
  </v-navigation-drawer>

  <v-main class="dash-main">
    <KalugaMapCanvas />
  </v-main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import ClientsOrdersTab from './ClientsOrdersTab.vue'
import FleetTrucksTab from './FleetTrucksTab.vue'
import KalugaMapCanvas from '@/sections/map-routing/KalugaMapCanvas.vue'
import WeatherControlBar from './WeatherControlBar.vue'
import RoutesTcoTab from './RoutesTcoTab.vue'
import WarehousesStockTab from './WarehousesStockTab.vue'
import { useErpStore } from './useErpStore'
import { formatDateTime } from '@/shared/utils/format'

const auth = useAuthStore()
const erp = useErpStore()
const router = useRouter()
const { mdAndUp } = useDisplay()

const DRAWER_MIN = 320
const DRAWER_MAX = 820
const DRAWER_DEFAULT = 400
const DRAWER_KEY = 'agrologistix-drawer-width'

const drawer = ref(mdAndUp.value)
const tab = ref('erp')
const isResizing = ref(false)
const drawerWidth = ref(readStoredWidth())

const loadedAtText = computed(() =>
  erp.loadedAt ? formatDateTime(erp.loadedAt) : 'ещё не загружено',
)

function readStoredWidth(): number {
  try {
    const stored = Number(localStorage.getItem(DRAWER_KEY))
    if (Number.isFinite(stored) && stored > 0) return clampWidth(stored)
  } catch {
    /* приватный режим: ширина останется дефолтной */
  }
  return DRAWER_DEFAULT
}

function clampWidth(value: number): number {
  const maxByViewport = Math.max(DRAWER_MIN, window.innerWidth - 420)
  return Math.min(Math.min(DRAWER_MAX, maxByViewport), Math.max(DRAWER_MIN, Math.round(value)))
}

function setDrawerWidth(value: number, persist = true): void {
  drawerWidth.value = clampWidth(value)
  if (!persist) return
  try {
    localStorage.setItem(DRAWER_KEY, String(drawerWidth.value))
  } catch {
    /* приватный режим: ширину не сохраняем */
  }
}

function nudgeDrawer(delta: number): void {
  setDrawerWidth(drawerWidth.value + delta)
}

let stopResize: (() => void) | null = null

function startResize(event: PointerEvent): void {
  const startX = event.clientX
  const startWidth = drawerWidth.value
  isResizing.value = true

  const onMove = (moveEvent: PointerEvent): void => {
    setDrawerWidth(startWidth + (moveEvent.clientX - startX), false)
  }
  const cleanup = (): void => {
    isResizing.value = false
    setDrawerWidth(drawerWidth.value)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', cleanup)
    window.removeEventListener('pointercancel', cleanup)
    stopResize = null
  }

  stopResize = cleanup
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', cleanup)
  window.addEventListener('pointercancel', cleanup)
}

onBeforeUnmount(() => {
  stopResize?.()
  erp.stopAutoSync()
})

onMounted(() => {
  void erp.loadState()
  // Раз в секунду подтягиваем состояние с сервера: store — единственный источник правды.
  erp.startAutoSync()
})

function reload(): void {
  void erp.loadState({ force: true })
}

function logout(): void {
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

.drawer-resizer {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 100%;
  padding: 0;
  border: none;
  border-left: var(--neu-border);
  background: rgba(242, 236, 251, 0.6);
  color: #5b5175;
  cursor: col-resize;
  touch-action: none;
  user-select: none;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.drawer-resizer:hover,
.drawer-resizer--active {
  background: rgba(109, 40, 217, 0.16);
  color: #5b21b6;
}

.drawer-resizer:focus-visible {
  outline-offset: -3px;
}

.drawer-head {
  margin-bottom: 12px;
}

.drawer-title {
  margin: 0;
  font-size: 18px;
}

.drawer-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #5b5175;
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
