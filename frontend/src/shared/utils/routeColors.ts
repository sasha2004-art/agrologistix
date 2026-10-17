/**
 * Цвета рейсов на карте и в таблице плана.
 *
 * Палитра рейсов: насыщенные, но приглушённые оттенки, различимые на
 * светлой подложке карты и не конфликтующие с цветами маркеров.
 */

export const ROUTE_COLORS = [
  '#6d28d9',
  '#047857',
  '#b45309',
  '#0369a1',
  '#be123c',
  '#4d7c0f',
] as const

export function routeColor(index: number): string {
  const safeIndex = Number.isFinite(index) && index >= 0 ? Math.floor(index) : 0
  return ROUTE_COLORS[safeIndex % ROUTE_COLORS.length]
}
