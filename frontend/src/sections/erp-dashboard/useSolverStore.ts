/**
 * Стор плана поставок: единственное место, где живёт ответ `POST /solver/optimize`.
 *
 * Расчёт — не мутация ERP, а вычисление на сервере: mock-fallback здесь
 * запрещён, иначе на карте и в TCO появятся «сохранённые» цифры, которых
 * сервер не считал.
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, optimize } from '@/shared/api/httpClient'
import type { Route, RouteStop, SolverResponse } from '@/shared/types/domain'
import { routeColor } from '@/shared/utils/routeColors'
import { freshnessLevel, type FreshnessLevel } from '@/shared/utils/freshness'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'

export type SolverStatus = 'idle' | 'loading' | 'ready' | 'error'

/** Стоп плана вместе с машиной и цветом рейса — для карты, таблицы и popup. */
export interface PlannedStop {
  stop: RouteStop
  truckId: number
  truckName: string
  color: string
  routeIndex: number
  freshness: FreshnessLevel
}

export const useSolverStore = defineStore('solver', () => {
  const auth = useAuthStore()

  const status = ref<SolverStatus>('idle')
  const plan = ref<SolverResponse | null>(null)
  const errorMessage = ref<string | null>(null)
  const calculatedAt = ref<Date | null>(null)

  const isLoading = computed(() => status.value === 'loading')
  const hasPlan = computed(() => plan.value !== null)
  const metrics = computed(() => plan.value?.metrics ?? null)
  const warnings = computed(() => plan.value?.warnings ?? [])
  const routes = computed<Route[]>(() => plan.value?.routes ?? [])
  /** `run_id` базового плана: с ним сравнивается сценарий «что, если». */
  const baselineRunId = computed(() => plan.value?.run_id ?? null)

  /** Машины плана с цветом рейса: для легенды и таблицы. */
  const routeLegend = computed(() =>
    routes.value.map((route, index) => ({
      truckId: route.truck_id,
      truckName: route.truck_name,
      color: routeColor(index),
      stops: route.stops.length,
      distanceKm: route.total_distance_km,
      costRub: route.total_cost_rub,
    })),
  )

  const routeColorByTruck = computed(() => {
    const map = new Map<number, string>()
    routes.value.forEach((route, index) => map.set(route.truck_id, routeColor(index)))
    return map
  })

  /** Плоский список стопов с цветом рейса и оценкой свежести. */
  const plannedStops = computed<PlannedStop[]>(() => {
    const result: PlannedStop[] = []
    routes.value.forEach((route, index) => {
      for (const stop of route.stops) {
        result.push({
          stop,
          truckId: route.truck_id,
          truckName: route.truck_name,
          color: routeColor(index),
          routeIndex: index,
          freshness: freshnessLevel(stop.expected_freshness),
        })
      }
    })
    return result
  })

  /** Стопы, которые стоит подсветить: свежесть ниже порога. */
  const riskyStops = computed(() =>
    plannedStops.value
      .filter((item) => item.freshness !== 'ok')
      .sort((a, b) => a.stop.expected_freshness - b.stop.expected_freshness),
  )

  function stopForOrder(orderId: number): PlannedStop | null {
    return plannedStops.value.find((item) => item.stop.order_id === orderId) ?? null
  }

  function stopForClient(clientId: number): PlannedStop | null {
    return plannedStops.value.find((item) => item.stop.client_id === clientId) ?? null
  }

  /** Расчёт базового плана. Повторный клик во время расчёта игнорируется. */
  async function optimizeBaseline(): Promise<void> {
    if (isLoading.value || !auth.accessPin) return
    status.value = 'loading'
    errorMessage.value = null
    try {
      const response = await optimize({ mode: 'baseline' }, auth.accessPin)
      plan.value = response
      calculatedAt.value = new Date()
      status.value = 'ready'
    } catch (error) {
      // План не трогаем: старый расчёт остаётся валидным для сравнения.
      errorMessage.value = solverErrorMessage(error)
      status.value = 'error'
    }
  }

  /** Отдельные формулировки: у расчёта нет «несохранённого изменения», есть «нет плана». */
  function solverErrorMessage(error: unknown): string {
    if (error instanceof ApiError) {
      if (error.status === 401) return 'PIN-код не принят: войдите заново, чтобы рассчитать план.'
      if (error.status === 422) return `Сервер отклонил запрос расчёта: ${error.detail}`
      if (error.status >= 500)
        return `Сервер не смог рассчитать план (${error.status}). Повторите попытку.`
      return error.detail
    }
    if (error instanceof TypeError)
      return 'Сервер недоступен: план не рассчитан. Проверьте соединение и повторите.'
    if (error instanceof Error) return error.message
    return 'Не удалось рассчитать план. Попробуйте ещё раз.'
  }

  function clear(): void {
    plan.value = null
    status.value = 'idle'
    errorMessage.value = null
    calculatedAt.value = null
  }

  return {
    status,
    plan,
    errorMessage,
    calculatedAt,
    isLoading,
    hasPlan,
    metrics,
    warnings,
    routes,
    baselineRunId,
    routeLegend,
    routeColorByTruck,
    plannedStops,
    riskyStops,
    stopForOrder,
    stopForClient,
    optimizeBaseline,
    clear,
  }
})
