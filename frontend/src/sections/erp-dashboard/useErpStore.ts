/**
 * Типизированный store исходного ERP-состояния (Day 3).
 *
 * Источник правды — `GET /api/v1/erp/state`. Store только читает и кэширует
 * ответ API; любые изменения (цена, статус заявки, поломка машины) на Day 4
 * выполняются через PATCH и последующий `loadState({ force: true })`.
 */

import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  describeApiError,
  fetchErpState,
  patchOrder,
  patchStock,
  patchTruck,
} from '@/shared/api/httpClient'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import { useNotificationStore } from '@/shared/stores/useNotificationStore'
import { formatKg, formatPercent } from '@/shared/utils/format'
import { freshnessLevel } from '@/shared/utils/freshness'
import { useSolverStore } from './useSolverStore'
import type {
  Client,
  ClientOrder,
  ClientOrderPatch,
  DataSource,
  ERPState,
  Product,
  TruckPatch,
  Warehouse,
  WarehouseStock,
  WarehouseStockPatch,
} from '@/shared/types/domain'

export type ErpLoadStatus = 'idle' | 'loading' | 'ready' | 'error'
export type RiskSeverity = 'info' | 'warning' | 'error'

export interface StockRow {
  stock: WarehouseStock
  warehouse: Warehouse
  product: Product
}

export interface StockMatrixCell {
  product: Product
  stock: WarehouseStock | null
  available_kg: number
}

export interface StockMatrixRow {
  warehouse: Warehouse
  cells: StockMatrixCell[]
  total_kg: number
}

export interface OrderRow {
  order: ClientOrder
  client: Client
  product: Product
}

export interface RiskAlert {
  id: string
  severity: RiskSeverity
  message: string
}

/** Outstanding weight of an order: what is still undelivered after every PATCH. */
export function remainingKg(order: ClientOrder): number {
  return Math.max(0, order.requested_kg - order.delivered_kg)
}

/** Ключ массовой отметки доставки: по нему UI рисует общий индикатор. */
export const ORDERS_DELIVER_KEY = 'orders:deliver'

export const useErpStore = defineStore('erp', () => {
  const auth = useAuthStore()
  const notifications = useNotificationStore()
  const solver = useSolverStore()

  const state = ref<ERPState | null>(null)
  const status = ref<ErpLoadStatus>('idle')
  const errorMessage = ref<string | null>(null)
  const source = ref<DataSource>('api')
  const loadedAt = ref<Date | null>(null)
  /** Ключи вида `order:3` — по ним рисуются per-row индикаторы сохранения. */
  const pendingKeys = ref<Set<string>>(new Set())

  const warehouses = computed(() => state.value?.warehouses ?? [])
  const products = computed(() => state.value?.products ?? [])
  const stocks = computed(() => state.value?.stocks ?? [])
  const clients = computed(() => state.value?.clients ?? [])
  const orders = computed(() => state.value?.orders ?? [])
  const trucks = computed(() => state.value?.trucks ?? [])

  const isLoading = computed(() => status.value === 'loading')
  const hasError = computed(() => status.value === 'error')
  const isReady = computed(() => status.value === 'ready')
  const isEmpty = computed(
    () =>
      isReady.value &&
      warehouses.value.length === 0 &&
      clients.value.length === 0 &&
      orders.value.length === 0,
  )

  function indexBy<T, K extends keyof T>(items: T[], key: K): Map<T[K], T> {
    return new Map(items.map((item) => [item[key], item]))
  }

  const warehouseById = computed(() => indexBy(warehouses.value, 'id'))
  const productById = computed(() => indexBy(products.value, 'id'))
  const clientById = computed(() => indexBy(clients.value, 'id'))
  const truckById = computed(() => indexBy(trucks.value, 'id'))

  const stockMatrix = computed<StockMatrixRow[]>(() =>
    warehouses.value.map((warehouse) => {
      const cells = products.value.map((product) => {
        const stock =
          stocks.value.find(
            (item) => item.warehouse_id === warehouse.id && item.product_id === product.id,
          ) ?? null
        return { product, stock, available_kg: stock?.available_kg ?? 0 }
      })
      return {
        warehouse,
        cells,
        total_kg: cells.reduce((sum, cell) => sum + cell.available_kg, 0),
      }
    }),
  )

  const stockRows = computed<StockRow[]>(() =>
    stocks.value.flatMap((stock) => {
      const warehouse = warehouseById.value.get(stock.warehouse_id)
      const product = productById.value.get(stock.product_id)
      return warehouse && product ? [{ stock, warehouse, product }] : []
    }),
  )

  const orderRows = computed<OrderRow[]>(() =>
    orders.value.flatMap((order) => {
      const client = clientById.value.get(order.client_id)
      const product = productById.value.get(order.product_id)
      return client && product ? [{ order, client, product }] : []
    }),
  )

  const pendingOrders = computed(() =>
    orderRows.value.filter((row) => row.order.delivery_status === 'pending'),
  )
  const activeTrucks = computed(() => trucks.value.filter((truck) => truck.status === 'active'))
  const brokenTrucks = computed(() => trucks.value.filter((truck) => truck.status === 'broken'))
  const reeferTrucks = computed(() => trucks.value.filter((truck) => truck.has_reefer))
  const dirtCapableTrucks = computed(() =>
    trucks.value.filter((truck) => truck.can_use_dirt && truck.status === 'active'),
  )

  const dirtClients = computed(() => clients.value.filter((client) => client.road_type === 'dirt'))

  /** Быстрые индикаторы риска для левой панели (см. user-flow §3). */
  const riskAlerts = computed<RiskAlert[]>(() => {
    const alerts: RiskAlert[] = []

    if (isReady.value && activeTrucks.value.length === 0) {
      alerts.push({
        id: 'no-active-trucks',
        severity: 'error',
        message: 'Нет машин в строю: все заказы останутся не привезёнными.',
      })
    }

    // Часть парка сломана: расчёт пройдёт, но часть груза придётся распределить иначе.
    if (isReady.value && brokenTrucks.value.length > 0 && activeTrucks.value.length > 0) {
      const names = brokenTrucks.value.map((truck) => truck.name).join(', ')
      alerts.push({
        id: 'broken-trucks',
        severity: 'info',
        message: `Сломано машин: ${brokenTrucks.value.length} (${names}) — в расчёте не участвуют.`,
      })
    }

    if (isReady.value && dirtClients.value.length > 0 && dirtCapableTrucks.value.length === 0) {
      alerts.push({
        id: 'no-dirt-capable-truck',
        severity: 'error',
        message:
          'Ни одной машины, которая может ехать по грунтовке: заказы в такие точки останутся без поставки.',
      })
    }

    if (isReady.value && reeferTrucks.value.length === 0) {
      alerts.push({
        id: 'no-reefer',
        severity: 'warning',
        message: 'Нет машин с охлаждением: урожай будет портиться быстрее.',
      })
    }

    const stockByProduct = new Map<number, number>()
    for (const stock of stocks.value) {
      stockByProduct.set(
        stock.product_id,
        (stockByProduct.get(stock.product_id) ?? 0) + stock.available_kg,
      )
    }
    // Партия может испортиться ещё на складе: свежесть ниже порога — риск порчи.
    for (const stock of stocks.value) {
      const level = freshnessLevel(stock.initial_freshness)
      if (level === 'ok') continue
      const warehouse = warehouseById.value.get(stock.warehouse_id)
      const product = productById.value.get(stock.product_id)
      alerts.push({
        id: `low-freshness-${stock.id}`,
        severity: level === 'error' ? 'error' : 'warning',
        message: `${product?.name ?? `Урожай №${stock.product_id}`} на складе «${
          warehouse?.name ?? `№${stock.warehouse_id}`
        }»: сохранность партии ${formatPercent(stock.initial_freshness * 100)}, остаток ${formatKg(
          stock.available_kg,
        )} — урожай рискует испортиться.`,
      })
    }

    for (const row of pendingOrders.value) {
      const outstanding = remainingKg(row.order)
      const available = stockByProduct.get(row.order.product_id) ?? 0
      if (outstanding > 0 && available < outstanding) {
        alerts.push({
          id: `stock-shortage-${row.order.id}`,
          severity: 'warning',
          message: `${row.product.name}: остаток ${Math.round(available)} кг меньше заказа №${row.order.id} (${Math.round(outstanding)} кг).`,
        })
      }
    }

    return alerts
  })

  /** Готовое состояние для общего StatePanel: loading → empty → error → ready. */
  const panelStatus = computed<'loading' | 'empty' | 'error' | 'ready'>(() => {
    if (isLoading.value) return 'loading'
    if (hasError.value && state.value === null) return 'error'
    if (isEmpty.value) return 'empty'
    return 'ready'
  })

  const errorAlerts = computed(() => riskAlerts.value.filter((alert) => alert.severity === 'error'))
  const warningAlerts = computed(() =>
    riskAlerts.value.filter((alert) => alert.severity === 'warning'),
  )

  async function loadState(
    options: { force?: boolean; silent?: boolean; quiet?: boolean } = {},
  ): Promise<void> {
    if (!auth.accessPin) {
      status.value = 'error'
      errorMessage.value = 'Требуется вход по коду доступа.'
      return
    }
    if (status.value === 'loading') return
    if (status.value === 'ready' && !options.force && !options.silent) return

    if (!options.silent) {
      status.value = 'loading'
      errorMessage.value = null
    }
    try {
      const result = await fetchErpState(auth.accessPin)
      state.value = result.data
      source.value = result.source
      loadedAt.value = new Date()
      status.value = 'ready'
    } catch (error) {
      const message = describeApiError(error)
      // quiet — фоновый опрос: разовая сеть-ошибка не должна спамить уведомлениями.
      if (!options.quiet) notifications.push('error', message)
      if (options.silent || options.quiet) {
        // Тихий refetch: данные уже применены, состояние не ломаем.
        return
      }
      errorMessage.value = message
      status.value = 'error'
    }
  }

  /**
   * Фоновая синхронизация со сервером: раз в секунду перечитываем состояние,
   * чтобы карта, таблицы и KPI всегда жили от одного источника правды — store.
   * Ошибки глушим: следующий тик всё равно попробует снова.
   */
  const SYNC_INTERVAL_MS = 1000
  const isSyncing = ref(false)
  let syncTimer: number | null = null

  async function syncTick(): Promise<void> {
    if (!auth.accessPin || isSyncing.value || status.value === 'loading') return
    isSyncing.value = true
    try {
      await loadState({ force: true, silent: true, quiet: true })
    } finally {
      isSyncing.value = false
    }
  }

  function startAutoSync(intervalMs: number = SYNC_INTERVAL_MS): void {
    stopAutoSync()
    if (typeof window === 'undefined') return
    syncTimer = window.setInterval(() => void syncTick(), intervalMs)
  }

  function stopAutoSync(): void {
    if (syncTimer !== null) {
      window.clearInterval(syncTimer)
      syncTimer = null
    }
  }

  function isPending(key: string): boolean {
    return pendingKeys.value.has(key)
  }

  function replaceById<T extends { id: number }>(items: T[], updated: T): T[] {
    return items.map((item) => (item.id === updated.id ? updated : item))
  }

  /**
   * Единый путь мутации: PATCH → применение ответа → тихий refetch актуального состояния.
   * Локальный store никогда не остаётся единственным источником правды.
   */
  async function runMutation(
    key: string,
    notice: string,
    mutate: (accessPin: string) => Promise<void>,
  ): Promise<boolean> {
    const accessPin = auth.accessPin
    if (!accessPin) {
      notifications.push('error', 'Требуется вход по коду доступа.')
      return false
    }
    pendingKeys.value.add(key)
    try {
      await mutate(accessPin)
      notifications.push('success', notice)
      await loadState({ force: true, silent: true })
      // Изменение ERP делает посчитанный план устаревшим: стор солвера
      // подсветит, что исходные данные изменились, и логист пересчитает план.
      solver.markPlanStale()
      return true
    } catch (error) {
      notifications.push('error', describeApiError(error))
      return false
    } finally {
      pendingKeys.value.delete(key)
    }
  }

  function updateOrder(orderId: number, patch: ClientOrderPatch): Promise<boolean> {
    if (patch.purchase_price_rub === undefined && patch.delivery_status === undefined) {
      // Backend отвечает 400 на пустой патч — не отправляем заведомо невалидный запрос.
      return Promise.resolve(false)
    }
    return runMutation(`order:${orderId}`, `Заказ №${orderId} сохранён`, async (accessPin) => {
      const updated = await patchOrder(orderId, patch, accessPin)
      if (state.value) state.value.orders = replaceById(state.value.orders, updated)
    })
  }

  function updateTruck(truckId: number, patch: TruckPatch): Promise<boolean> {
    return runMutation(`truck:${truckId}`, `Машина №${truckId} обновлена`, async (accessPin) => {
      const updated = await patchTruck(truckId, patch, accessPin)
      if (state.value) state.value.trucks = replaceById(state.value.trucks, updated)
    })
  }

  function updateStock(stockId: number, patch: WarehouseStockPatch): Promise<boolean> {
    return runMutation(`stock:${stockId}`, 'Остаток склада обновлён', async (accessPin) => {
      const updated = await patchStock(stockId, patch, accessPin)
      if (state.value) state.value.stocks = replaceById(state.value.stocks, updated)
    })
  }

  /**
   * Массовая отметка заказов доставленными: по одному PATCH на заказ — бэкенд
   * списывает сток по стопам последнего плана. Затем один перезапрос состояния,
   * одно уведомление и пометка плана устаревшим, а не по тосту на заказ.
   * На ошибке (обычно 409: остаток склада изменился после расчёта) останавливаемся:
   * продолжать списание по устаревшему плану нельзя, тосты сообщат, сколько успело.
   */
  async function deliverOrders(orderIds: number[]): Promise<boolean> {
    const accessPin = auth.accessPin
    if (!accessPin) {
      notifications.push('error', 'Требуется вход по коду доступа.')
      return false
    }
    const unique = [...new Set(orderIds)]
    if (unique.length === 0) return false

    pendingKeys.value.add(ORDERS_DELIVER_KEY)
    let done = 0
    let failure: unknown = null
    try {
      for (const orderId of unique) {
        try {
          const updated = await patchOrder(orderId, { delivery_status: 'delivered' }, accessPin)
          if (state.value) state.value.orders = replaceById(state.value.orders, updated)
          done += 1
        } catch (error) {
          failure = error
          break
        }
      }
    } finally {
      pendingKeys.value.delete(ORDERS_DELIVER_KEY)
    }

    if (done > 0) {
      await loadState({ force: true, silent: true })
      solver.markPlanStale()
      notifications.push('success', `Отмечено доставленными: ${done} из ${unique.length}`)
    }
    if (failure) notifications.push('error', describeApiError(failure))
    return done > 0 && failure === null
  }

  function clear(): void {
    state.value = null
    status.value = 'idle'
    errorMessage.value = null
    loadedAt.value = null
    pendingKeys.value.clear()
    notifications.clear()
  }
  watch(
    () => auth.isAuthenticated,
    (isAuthenticated) => {
      if (!isAuthenticated) {
        stopAutoSync()
        clear()
      }
    },
  )

  return {
    state,
    status,
    errorMessage,
    source,
    loadedAt,
    pendingKeys,
    isLoading,
    hasError,
    isReady,
    isEmpty,
    warehouses,
    products,
    stocks,
    clients,
    orders,
    trucks,
    warehouseById,
    productById,
    clientById,
    truckById,
    stockMatrix,
    stockRows,
    orderRows,
    pendingOrders,
    activeTrucks,
    brokenTrucks,
    reeferTrucks,
    dirtCapableTrucks,
    dirtClients,
    panelStatus,
    riskAlerts,
    errorAlerts,
    warningAlerts,
    loadState,
    isSyncing,
    syncTick,
    startAutoSync,
    stopAutoSync,
    isPending,
    updateOrder,
    updateTruck,
    updateStock,
    deliverOrders,
    clear,
  }
})
