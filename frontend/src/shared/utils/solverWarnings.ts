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
    title: 'Сломанные машины исключены',
  },
  no_active_trucks: {
    icon: 'mdi-truck-remove-outline',
    title: 'Нет машин в строю',
  },
  unmet_demand: {
    icon: 'mdi-package-variant-closed-remove',
    title: 'Недовоз',
  },
  dirt_unreachable: {
    icon: 'mdi-road-variant',
    title: 'Грунтовка недоступна',
  },
  heat_without_reefer: {
    icon: 'mdi-thermometer-high',
    title: 'Жара без рефрижератора',
  },
  stock_shortage: {
    icon: 'mdi-warehouse',
    title: 'Нехватка остатков',
  },
}

export function warningMeta(code: string): WarningMeta {
  return WARNING_META[code] ?? { icon: 'mdi-alert-outline', title: 'Предупреждение расчёта' }
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
  if (warning.order_id) return `Заявка №${warning.order_id}`
  if (warning.client_id) return `Клиент №${warning.client_id}`
  return null
}
