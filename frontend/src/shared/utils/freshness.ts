/**
 * Пороги свежести партий и стопов плана.
 *
 * Значения согласованы с формулой `E[Freshness] = exp(-λ_p · t · k_temp)`
 * (см. `backend/app/services/freshness_math.py`): клубника теряет ~8 % свежести
 * в час при +20 °C без рефа, поэтому 0.90 — это уже заметный риск порчи,
 * а 0.80 — существенное обесценивание груза.
 */

export const FRESHNESS_WARNING = 0.9
export const FRESHNESS_ERROR = 0.8

export type FreshnessLevel = 'ok' | 'warning' | 'error'

export function freshnessLevel(fraction: number): FreshnessLevel {
  if (fraction < FRESHNESS_ERROR) return 'error'
  if (fraction < FRESHNESS_WARNING) return 'warning'
  return 'ok'
}

export function freshnessLabel(fraction: number): string {
  const level = freshnessLevel(fraction)
  if (level === 'error') return 'Низкая сохранность'
  if (level === 'warning') return 'Сниженная сохранность'
  return 'Сохранность в норме'
}
