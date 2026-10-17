/** Единые правила числового форматирования для dashboard и печатных листов. */

const numberFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
const decimalFormatter = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})
const rubFormatter = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
})

export function formatDecimal(value: number): string {
  return decimalFormatter.format(value)
}

export function formatRub(value: number): string {
  return rubFormatter.format(value)
}

export function formatKg(value: number): string {
  return `${numberFormatter.format(value)} кг`
}

export function formatKm(value: number): string {
  return `${decimalFormatter.format(value)} км`
}

/** Доля 0..1 → проценты для отображения (например, свежесть). */
export function formatFreshness(fraction: number): string {
  return `${decimalFormatter.format(fraction * 100)} %`
}

/** Значение 0..100 → проценты. */
export function formatPercent(value: number): string {
  return `${decimalFormatter.format(value)} %`
}

/** Длительность в минутах → «45 мин» или «2 ч 05 мин». */
export function formatMinutes(value: number): string {
  const total = Math.max(0, Math.round(value))
  if (total < 60) return `${total} мин`
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  return minutes === 0 ? `${hours} ч` : `${hours} ч ${String(minutes).padStart(2, '0')} мин`
}

export function formatDateTime(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value)
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
