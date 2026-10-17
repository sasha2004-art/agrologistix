/**
 * Подбор машины и маршрута для заявки, которую берут «В работе».
 *
 * Стор ничего не пишет в ERP: он вызывает `POST /erp/orders/{id}/assign`,
 * запоминает оптимальный вариант для показа в таблице заказов и уведомляет
 * логиста. Данные живут в памяти сессии и очищаются при выходе.
 */

import { ref } from 'vue'
import { defineStore } from 'pinia'
import { assignOrder, describeApiError } from '@/shared/api/httpClient'
import type { AssignmentInfo, FixedAssignment } from '@/shared/types/domain'
import { formatFreshness, formatKm, formatMinutes } from '@/shared/utils/format'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import { useNotificationStore } from '@/shared/stores/useNotificationStore'

/** Компактная строка назначения: машина, склад, плечо, время и сохранность. */
export function assignmentSummary(assignment: AssignmentInfo): string {
  return [
    assignment.truck_name,
    assignment.warehouse_name,
    formatKm(assignment.distance_km),
    formatMinutes(assignment.duration_min),
    `сохранность ${formatFreshness(assignment.expected_freshness)}`,
  ].join(' · ')
}

export const useAssignmentStore = defineStore('assignment', () => {
  const auth = useAuthStore()
  const notifications = useNotificationStore()

  const assignments = ref<Record<number, AssignmentInfo>>({})
  const pending = ref<Set<number>>(new Set())
  /** Заявки, для которых автоподтяжка фиксации уже выполнялась в этой сессии. */
  const synced = ref<Set<number>>(new Set())

  function forOrder(orderId: number): AssignmentInfo | undefined {
    return assignments.value[orderId]
  }

  /**
   * Синхронизация с сервером: `GET /erp/state` возвращает сохранённые фиксации,
   * поэтому карта и подсказки восстанавливаются после перезагрузки.
   */
  function hydrate(items: FixedAssignment[]): void {
    assignments.value = Object.fromEntries(items.map((item) => [item.order_id, item]))
  }

  function isPending(orderId: number): boolean {
    return pending.value.has(orderId)
  }

  /**
   * Оптимальный вариант для заявки; `null` — подбор не удался.
   * `silent` нужен для массовых действий и автоподтяжки: тост покажет вызывающий.
   */
  async function assign(orderId: number, silent = false): Promise<AssignmentInfo | null> {
    const pin = auth.accessPin
    if (!pin || pending.value.has(orderId)) return assignments.value[orderId] ?? null

    pending.value.add(orderId)
    try {
      const assignment = await assignOrder(orderId, pin)
      assignments.value = { ...assignments.value, [orderId]: assignment }
      if (!silent) notifications.push('success', `Оптимально: ${assignmentSummary(assignment)}`)
      return assignment
    } catch (error) {
      if (!silent) notifications.push('error', describeApiError(error))
      return null
    } finally {
      pending.value.delete(orderId)
    }
  }

  /** Фиксация для нескольких заявок: тост выдаёт вызывающий, ошибки не спамят. */
  async function assignMany(orderIds: number[]): Promise<number> {
    let done = 0
    for (const orderId of orderIds) {
      if (await assign(orderId, true)) done += 1
    }
    return done
  }

  /**
   * Дотягивает фиксацию для заявок «В работе», у которых её нет: маршрут
   * появляется на карте, даже если статус поставили до подбора.
   */
  async function syncMissing(inProgressOrderIds: number[]): Promise<void> {
    const missing = inProgressOrderIds.filter(
      (orderId) => !assignments.value[orderId] && !synced.value.has(orderId),
    )
    if (missing.length === 0) return
    for (const orderId of missing) synced.value.add(orderId)
    await assignMany(missing)
  }

  function clear(): void {
    assignments.value = {}
    pending.value = new Set()
    synced.value = new Set()
  }

  return {
    assignments,
    pending,
    forOrder,
    hydrate,
    isPending,
    assign,
    assignMany,
    syncMissing,
    clear,
  }
})
