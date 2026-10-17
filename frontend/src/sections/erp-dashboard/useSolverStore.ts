/**
 * Стор планов поставок: база (`mode=baseline`) и сценарий «что, если» (`mode=what_if`).
 *
 * После каждой успешной мутации ERP сценарий пересчитывается относительно
 * сохранённого `baseline_run_id`; базовый план при этом не перезаписывается —
 * он остаётся точкой сравнения для окна «Было / Стало».
 *
 * Расчёт — вычисление на сервере, mock-fallback здесь запрещён: выдуманные
 * цифры на экране диспетчера хуже честной ошибки.
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, optimize } from '@/shared/api/httpClient'
import type { ComparisonDelta, Route, RouteStop, SolverResponse } from '@/shared/types/domain'
import { routeColor } from '@/shared/utils/routeColors'
import { freshnessLevel, type FreshnessLevel } from '@/shared/utils/freshness'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'

export type SolverStatus = 'idle' | 'loading' | 'ready' | 'error'
export type SolverRunKind = 'baseline' | 'what_if'
/** Какой план показывают карта, таблица и метрики. */
export type PlanView = 'baseline' | 'scenario'

/** Стоп плана вместе с машиной и цветом рейса — для карты, таблицы и popup. */
export interface PlannedStop {
  stop: RouteStop
  truckId: number
  truckName: string
  color: string
  routeIndex: number
  freshness: FreshnessLevel
}

/** Пауза перед пересчётом сценария: серия PATCH не должна давать серию расчётов. */
const SCENARIO_DEBOUNCE_MS = 400

export const useSolverStore = defineStore('solver', () => {
  const auth = useAuthStore()

  const status = ref<SolverStatus>('idle')
  const runKind = ref<SolverRunKind>('baseline')
  const baseline = ref<SolverResponse | null>(null)
  const scenario = ref<SolverResponse | null>(null)
  const view = ref<PlanView>('baseline')
  const errorMessage = ref<string | null>(null)
  const calculatedAt = ref<Date | null>(null)
  /** ERP изменился после последнего сценария — сравнение ещё не обновлено. */
  const scenarioStale = ref(false)

  let debounceTimer: number | null = null

  const isLoading = computed(() => status.value === 'loading')
  const isRunning = computed(() => runKind.value)
  const hasBaseline = computed(() => baseline.value !== null)
  const hasScenario = computed(() => scenario.value !== null)
  const comparison = computed<ComparisonDelta | null>(() => scenario.value?.comparison ?? null)
  const baselineRunId = computed(() => baseline.value?.run_id ?? null)

  /** План, который сейчас на экране. */
  const activePlan = computed<SolverResponse | null>(() =>
    view.value === 'scenario' ? scenario.value : baseline.value,
  )
  const activeLabel = computed(() =>
    view.value === 'scenario' ? 'Сценарий «что, если»' : 'Базовый план',
  )
  const metrics = computed(() => activePlan.value?.metrics ?? null)
  const warnings = computed(() => activePlan.value?.warnings ?? [])
  const routes = computed<Route[]>(() => activePlan.value?.routes ?? [])

  /**
   * Порядок машин одинаков для базы и сценария, поэтому машина сохраняет цвет
   * при переключении вида — сравнивать планы глазами проще.
   */
  const truckOrder = computed(() => {
    const ids: number[] = []
    for (const plan of [baseline.value, scenario.value]) {
      for (const route of plan?.routes ?? []) {
        if (!ids.includes(route.truck_id)) ids.push(route.truck_id)
      }
    }
    return ids
  })

  const routeColorByTruck = computed(() => {
    const map = new Map<number, string>()
    truckOrder.value.forEach((truckId, index) => map.set(truckId, routeColor(index)))
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

  /** Плоский список стопов активного плана: свежесть и цвет рейса. */
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

  /** Краткая сводка сравнения для чипа: «+30,2 % TCO», «без изменений TCO». */
  const tcoDeltaLabel = computed(() => {
    const pct = comparison.value?.total_tco_rub.delta_pct ?? null
    if (pct === null) return 'Δ TCO'
    if (Math.abs(pct) < 0.05) return 'без изменений TCO'
    const sign = pct > 0 ? '+' : '−'
    return `${sign}${Math.abs(pct).toFixed(1).replace('.', ',')} % TCO`
  })

  /** Дельта положительная и по TCO — значит сценарий дороже базового. */
  const tcoDeltaWorse = computed(() => (comparison.value?.total_tco_rub.delta ?? 0) > 0)

  /** Стопы, которые стоит подсветить: свежесть ниже порога. */
  const riskyStops = computed(() =>
    plannedStops.value
      .filter((item) => item.freshness !== 'ok')
      .sort((a, b) => a.stop.expected_freshness - b.stop.expected_freshness),
  )

  function colorOf(truckId: number): string {
    return routeColorByTruck.value.get(truckId) ?? routeColor(0)
  }

  function stopForOrder(orderId: number): PlannedStop | null {
    return plannedStops.value.find((item) => item.stop.order_id === orderId) ?? null
  }

  function stopForClient(clientId: number): PlannedStop | null {
    return plannedStops.value.find((item) => item.stop.client_id === clientId) ?? null
  }

  /** Базовый план: стартовая точка для всех сценариев. */
  async function optimizeBaseline(): Promise<void> {
    if (isLoading.value || !auth.accessPin) return
    await run('baseline')
  }

  /** Сценарий «что, если»: сервер сам читает актуальные PATCH-изменения. */
  async function runScenario(): Promise<void> {
    if (isLoading.value || !auth.accessPin || !baseline.value) return
    await run('what_if')
  }

  async function run(kind: SolverRunKind): Promise<void> {
    const pin = auth.accessPin
    if (!pin) return
    status.value = 'loading'
    runKind.value = kind
    errorMessage.value = null
    try {
      const request =
        kind === 'what_if'
          ? { mode: 'what_if' as const, baseline_run_id: baseline.value?.run_id ?? 0 }
          : { mode: 'baseline' as const }
      const response = await optimize(request, pin)
      if (kind === 'what_if') {
        scenario.value = response
        scenarioStale.value = false
      } else {
        baseline.value = response
        // Новый базовый план обнуляет сравнение: старый сценарий к нему не относится.
        scenario.value = null
        view.value = 'baseline'
        scenarioStale.value = false
      }
      calculatedAt.value = new Date()
      status.value = 'ready'
    } catch (error) {
      // Планы не трогаем: неудачный пересчёт не должен стирать прошлый результат.
      errorMessage.value = solverErrorMessage(error)
      status.value = 'error'
    }
  }

  /**
   * Вызывается после успешного PATCH: сценарий устарел, а если база уже есть —
   * пересчитываем его автоматически (с коротким дебаунсом на серию изменений).
   */
  function afterMutation(): void {
    scenarioStale.value = true
    if (!baseline.value) return
    if (debounceTimer !== null) window.clearTimeout(debounceTimer)
    debounceTimer = window.setTimeout(() => {
      debounceTimer = null
      void runScenario()
    }, SCENARIO_DEBOUNCE_MS)
  }

  function setView(next: PlanView): void {
    if (next === 'scenario' && !scenario.value) return
    view.value = next
  }

  function cancelPending(): void {
    if (debounceTimer !== null) {
      window.clearTimeout(debounceTimer)
      debounceTimer = null
    }
  }

  function clear(): void {
    cancelPending()
    baseline.value = null
    scenario.value = null
    view.value = 'baseline'
    status.value = 'idle'
    runKind.value = 'baseline'
    errorMessage.value = null
    calculatedAt.value = null
    scenarioStale.value = false
  }

  /** Отдельные формулировки: у расчёта нет «несохранённого изменения», есть «нет плана». */
  function solverErrorMessage(error: unknown): string {
    if (error instanceof ApiError) {
      if (error.status === 401) return 'PIN-код не принят: войдите заново, чтобы рассчитать план.'
      if (error.status === 404) return 'Базовый план не найден на сервере — рассчитайте его заново.'
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
    runKind,
    baseline,
    scenario,
    view,
    errorMessage,
    calculatedAt,
    scenarioStale,
    isLoading,
    isRunning,
    hasBaseline,
    hasScenario,
    comparison,
    baselineRunId,
    activePlan,
    activeLabel,
    metrics,
    warnings,
    routes,
    routeLegend,
    routeColorByTruck,
    plannedStops,
    riskyStops,
    tcoDeltaLabel,
    tcoDeltaWorse,
    optimizeBaseline,
    runScenario,
    afterMutation,
    setView,
    clear,
    stopForOrder,
    stopForClient,
  }
})
