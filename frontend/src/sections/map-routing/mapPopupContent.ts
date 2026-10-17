/**
 * HTML-содержимое карточки объекта: адрес, статус и список заявок. Разметка
 * собирается строками, потому что Mapbox Popup принимает HTML, а не Vue-компонент.
 * Карточка открывается только по нажатию на маркер.
 *
 * Полная карточка перечисляет заявки покупателя кнопками: подробности по каждой
 * заявке раскрываются нажатием и живут в DOM popup, поэтому обработчики
 * навешиваются делегированием на контейнер (`bindOrderToggles`).
 */

import type { Popup } from 'mapbox-gl'
import {
  formatFreshness,
  formatKg,
  formatKm,
  formatMinutes,
  formatRub,
} from '@/shared/utils/format'
import { statusLabel, type MapPoint, type MapPointOrder } from './mapPoints'

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function detailRow(term: string, value: string): string {
  return (
    `<div class="map-popup__detail">` +
    `<span class="map-popup__detail-term">${escapeHtml(term)}</span>` +
    `<span class="map-popup__detail-value">${value}</span>` +
    `</div>`
  )
}

/** Подробности одной заявки: параметры заказа и, если есть, данные рейса. */
function orderDetailsHtml(order: MapPointOrder): string {
  const rows = [
    detailRow('Урожай', escapeHtml(order.productName)),
    detailRow('Заявлено', formatKg(order.requestedKg)),
    detailRow('Цена', `${formatRub(order.purchasePriceRub)} / кг`),
    detailRow('Штраф за недовоз', `${formatRub(order.unmetPenaltyRub)} / кг`),
    detailRow('Уже доставлено', formatKg(order.deliveredKg)),
    detailRow('Статус', escapeHtml(statusLabel(order.deliveryStatus))),
  ]

  if (order.plan) {
    const extra = order.planStopsCount > 1 ? ` (+${order.planStopsCount - 1} остановок)` : ''
    rows.push(
      detailRow(
        'Машина',
        `<span class="map-popup__swatch" style="background:${escapeHtml(order.plan.color)}"></span>` +
          `${escapeHtml(order.plan.truckName)}${extra}`,
      ),
    )
    rows.push(detailRow('Остановка', `№${order.plan.sequenceOrder}`))
    rows.push(detailRow('Плечо', formatKm(order.plan.distanceKm)))
    rows.push(detailRow('В пути', formatMinutes(order.plan.etaMinutes)))
    rows.push(detailRow('Сохранность', formatFreshness(order.plan.expectedFreshness)))
    rows.push(detailRow('Отгружено', formatKg(order.plan.shippedKg)))
    rows.push(detailRow('Стоимость плеча', formatRub(order.plan.tripLegCostRub)))
  }

  return rows.join('')
}

function orderBlockHtml(order: MapPointOrder): string {
  const detailsId = `map-popup-order-${order.orderId}`
  const title = `Заказ №${order.orderId} · ${order.productName} · ${formatKg(order.requestedKg)}`
  return (
    `<div class="map-popup__order">` +
    `<button type="button" class="map-popup__order-btn" aria-expanded="false" ` +
    `aria-controls="${detailsId}" data-order-toggle="${order.orderId}">` +
    `<span class="map-popup__order-title">${escapeHtml(title)}</span>` +
    `<span class="mdi mdi-chevron-down map-popup__order-chevron" aria-hidden="true"></span>` +
    `</button>` +
    `<div class="map-popup__order-details" id="${detailsId}" ` +
    `data-order-details="${order.orderId}" hidden>${orderDetailsHtml(order)}</div>` +
    `</div>`
  )
}

/** Полная карточка точки: адрес, статус и раскрывающийся список заявок. */
export function popupHtml(point: MapPoint): string {
  const rows: string[] = []
  if (point.address) rows.push(`<div class="map-popup__row">${escapeHtml(point.address)}</div>`)
  if (point.kind === 'client' && point.deliveryStatus) {
    rows.push(
      `<div class="map-popup__row">Статус: <strong>${escapeHtml(
        statusLabel(point.deliveryStatus),
      )}</strong></div>`,
    )
  }
  if (point.orders.length > 0) {
    rows.push(
      `<div class="map-popup__orders">` +
        `<div class="map-popup__orders-title">Заказы: ${point.orders.length} · ${formatKg(
          point.requestedKg,
        )}</div>` +
        point.orders.map(orderBlockHtml).join('') +
        `</div>`,
    )
  }

  return `<div class="map-popup"><strong>${escapeHtml(point.name)}</strong>${rows.join('')}</div>`
}

/**
 * Возвращает раскрытые блоки заявок к состоянию из `expanded`: `setHTML`
 * пересобирает разметку popup и сбрасывает подсказки, открытые пользователем.
 */
export function restoreOrderState(container: HTMLElement | undefined, expanded: Set<number>): void {
  if (!container) return
  for (const details of container.querySelectorAll<HTMLElement>('[data-order-details]')) {
    const orderId = Number(details.dataset.orderDetails)
    const open = expanded.has(orderId)
    details.hidden = !open
    const button = container.querySelector<HTMLButtonElement>(`[data-order-toggle="${orderId}"]`)
    button?.setAttribute('aria-expanded', String(open))
    button?.classList.toggle('map-popup__order-btn--open', open)
  }
}

/**
 * Делегирует клики по кнопкам заявок. Обработчик вешается на контейнер popup
 * один раз: `setHTML` заменяет содержимое, но сам контейнер остаётся прежним.
 */
export function bindOrderToggles(popup: Popup, expanded: Set<number>): void {
  const container = popup.getElement()
  if (!container || container.dataset.orderTogglesBound === 'true') return
  container.dataset.orderTogglesBound = 'true'
  container.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null
    const button = target?.closest<HTMLButtonElement>('[data-order-toggle]')
    if (!button) return
    // Клик по кнопке не должен доходить до карты: иначе Mapbox закроет popup.
    event.stopPropagation()
    const orderId = Number(button.dataset.orderToggle)
    if (expanded.has(orderId)) expanded.delete(orderId)
    else expanded.add(orderId)
    restoreOrderState(container, expanded)
  })
}
