/**
 * Централизованные всплывающие уведомления.
 *
 * Любой алерт об операции (успех/ошибка PATCH, ошибка загрузки) проходит
 * через этот store и показывается один раз в правом верхнем углу на 2 секунды.
 */

import { ref } from 'vue'
import { defineStore } from 'pinia'

export type NotificationType = 'success' | 'error' | 'warning' | 'info'

export interface AppNotification {
  id: number
  type: NotificationType
  text: string
}

/** Время показа одного уведомления, мс. */
export const NOTIFICATION_DISPLAY_MS = 2000

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<AppNotification[]>([])
  const timers = new Map<number, number>()
  let nextId = 1

  function dismiss(id: number): void {
    items.value = items.value.filter((item) => item.id !== id)
    const timer = timers.get(id)
    if (timer !== undefined) {
      window.clearTimeout(timer)
      timers.delete(id)
    }
  }

  function push(type: NotificationType, text: string): number {
    const id = nextId++
    items.value = [...items.value, { id, type, text }]
    timers.set(
      id,
      window.setTimeout(() => dismiss(id), NOTIFICATION_DISPLAY_MS),
    )
    return id
  }

  function clear(): void {
    for (const id of [...timers.keys()]) dismiss(id)
    items.value = []
    timers.clear()
  }

  return { items, push, dismiss, clear }
})
