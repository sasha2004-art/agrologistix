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
import type { OrderAssignment } from '@/shared/types/domain'
import { formatFreshness, formatKm, formatMinutes } from '@/shared/utils/format'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import { useNotificationStore } from '@/shared/stores/useNotificationStore'

/** Компактная строка назначения: машина, склад, плечо, время и сохранность. */
export function assignmentSummary(assignment: OrderAssignment): string {
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

  const assignments = ref<Record<number, OrderAssignment>>({})
  const pending = ref<Set<number>>(new Set())

  function forOrder(orderId: number): OrderAssignment | undefined {
    return assignments.value[orderId]
  }

  function isPending(orderId: number): boolean {
    return pending.value.has(orderId)
  }

  /** Оптимальный вариант для заявки; `null` — подбор не удался. */
  async function assign(orderId: number): Promise<OrderAssignment | null> {
    const pin = auth.accessPin
    if (!pin || pending.value.has(orderId)) return assignments.value[orderId] ?? null

    pending.value.add(orderId)
    try {
      const assignment = await assignOrder(orderId, pin)
      assignments.value = { ...assignments.value, [orderId]: assignment }
      notifications.push('success', `Оптимально: ${assignmentSummary(assignment)}`)
      return assignment
    } catch (error) {
      notifications.push('error', describeApiError(error))
      return null
    } finally {
      pending.value.delete(orderId)
    }
  }

  function clear(): void {
    assignments.value = {}
    pending.value = new Set()
  }

  return { assignments, pending, forOrder, isPending, assign, clear }
})
