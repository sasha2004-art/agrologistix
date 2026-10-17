/** Остаток спроса заказа: сколько ещё не отгружено после всех изменений статуса. */
export function remainingKg(order: { requested_kg: number; delivered_kg: number }): number {
  return Math.max(0, order.requested_kg - order.delivered_kg)
}
