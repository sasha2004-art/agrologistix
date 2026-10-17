/**
 * Стор плана поставок: единственный расчёт по актуальному состоянию ERP.
 *
 * Логист меняет заявки, машины, цены и погоду через PATCH-и, после чего стор
 * ERP помечает план устаревшим (`markPlanStale`), а пересчёт запускается
 * кнопкой «Рассчитать поставки». Сервер каждый раз читает актуальные данные
 * из SQLite, поэтому сценариев и режимов у расчёта нет.
 *
 * Расчёт — вычисление на сервере, mock-fallback здесь запрещён: выдуманные
 * цифры на экране диспетчера хуже честной ошибки.
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
  /** ERP изменился после расчёта — план нужно пересчитать. */
  const planStale = ref(false)

  const isLoading = computed(() => status.value === 'loading')
  const hasPlan = computed(() => plan.value !== null)
  const metrics = computed(() => plan.value?.metrics ?? null)
  const warnings = computed(() => plan.value?.warnings ?? [])
  const routes = computed<Route[]>(() => plan.value?.routes ?? [])

  const routeColorByTruck = computed(() => {
    const map = new Map<number, string>()
    routes.value.forEach((route, index) => map.set(route.truck_id, routeColor(index)))
    return map
  })

  const routeLegend = computed(() =>
    routes.value.map((route) => ({
      truckId: route.truck_id,
      truckName: route.truck_name,
      color: colorOf(route.truck_id),
      stops: route.stops.length,
      distanceKm: route.total_distance_km,
      costRub: route.total_cost_rub,
    })),
  )

  /** Плоский список стопов плана: свежесть и цвет рейса. */
  const plannedStops = computed<PlannedStop[]>(() => {
    const result: PlannedStop[] = []
    routes.value.forEach((route, index) => {
      for (const stop of route.stops) {
        result.push({
          stop,
          truckId: route.truck_id,
          truckName: route.truck_name,
          color: colorOf(route.truck_id),
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

  function colorOf(truckId: number): string {
    return routeColorByTruck.value.get(truckId) ?? routeColor(0)
  }

  /** Расчёт плана по текущему состоянию ERP и погоде. */
  async function optimizePlan(): Promise<void> {
    const pin = auth.accessPin
    if (isLoading.value || !pin) return
    status.value = 'loading'
    errorMessage.value = null
    try {
      const response = await optimize(pin)
      plan.value = response
      calculatedAt.value = new Date()
      planStale.value = false
      status.value = 'ready'
    } catch (error) {
      // План не трогаем: неудачный пересчёт не должен стирать прошлый результат.
      errorMessage.value = solverErrorMessage(error)
      status.value = 'error'
    }
  }

  /**
   * Вызывается после успешного PATCH: план остаётся на экране как справка,
   * но исходные данные уже другие, поэтому расчёт помечается устаревшим.
   */
  function markPlanStale(): void {
    if (plan.value) planStale.value = true
  }

  function clear(): void {
    plan.value = null
    status.value = 'idle'
    errorMessage.value = null
    calculatedAt.value = null
    planStale.value = false
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

  return {
    status,
    plan,
    errorMessage,
    calculatedAt,
    planStale,
    isLoading,
    hasPlan,
    metrics,
    warnings,
    routes,
    routeLegend,
    routeColorByTruck,
    plannedStops,
    riskyStops,
    optimizePlan,
    markPlanStale,
    clear,
  }
})
