/**
 * Расшифровка предупреждений солвера (`SolverWarning.code`) для UI.
 *
 * Бэкенд присылает код, сообщение и severity; код нужен, чтобы дать
 * предупреждению иконку и короткий заголовок, а текст — от сервера.
 */

import type { WarningSeverity } from '@/shared/types/domain'

export interface WarningMeta {
  icon: string
  title: string
}

const WARNING_META: Record<string, WarningMeta> = {
  broken_trucks_excluded: {
    icon: 'mdi-car-wrench',
    title: 'Машины не в работе',
  },
  no_active_trucks: {
    icon: 'mdi-truck-remove-outline',
    title: 'Нет машин в строю',
  },
  unmet_demand: {
    icon: 'mdi-package-variant-closed-remove',
    title: 'Недопоставка',
  },
  dirt_unreachable: {
    icon: 'mdi-road-variant',
    title: 'Нет машины для грунтовки',
  },
  heat_without_reefer: {
    icon: 'mdi-thermometer-high',
    title: 'Жара без рефрижератора',
  },
  stock_shortage: {
    icon: 'mdi-warehouse',
    title: 'Не хватает урожая на складе',
  },
  freshness_risk: {
    icon: 'mdi-thermometer-low',
    title: 'Низкая сохранность',
  },
  trip_limit_exceeded: {
    icon: 'mdi-clock-alert-outline',
    title: 'Слишком длинный рейс',
  },
}

export function warningMeta(code: string): WarningMeta {
  return WARNING_META[code] ?? { icon: 'mdi-alert-outline', title: 'Замечание к расчёту' }
}

export function warningColor(severity: WarningSeverity): string {
  if (severity === 'error') return 'error'
  if (severity === 'warning') return 'warning'
  return 'info'
}

/** Ссылка на заявку/клиента из предупреждения — для навигации по плану. */
export function warningTarget(warning: {
  order_id?: number | null
  client_id?: number | null
}): string | null {
  if (warning.order_id) return `Заказ №${warning.order_id}`
  if (warning.client_id) return `Покупатель №${warning.client_id}`
  return null
}
