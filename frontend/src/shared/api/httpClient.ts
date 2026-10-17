/**
 * Typed HTTP-клиент. Единственная точка общения с FastAPI.
 *
 * Контракт: заголовок `X-Access-Pin`, JSON в snake_case, ошибки формата
 * `{ code, detail, request_id? }` (см. `backend/app/schemas/error_schemas.py`).
 *
 * В dev-режиме при недоступном backend включается mock-fallback с тем же DTO,
 * чтобы экраны разрабатывались без запущенного API.
 */

import * as mockData from './mockData'
import type {
  AuthResponse,
  Client,
  ClientCreate,
  ClientOrder,
  ClientOrderCreate,
  ClientOrderPatch,
  DataSource,
  ERPState,
  Product,
  ProductCreate,
  ProductPatch,
  TruckCreate,
  WarehouseStockCreate,
  Loaded,
  OrderAssignment,
  SolverResponse,
  Truck,
  TruckPatch,
  ValidationErrorBody,
  WarehouseStock,
  WarehouseStockPatch,
  WeatherMode,
  WeatherResponse,
} from '@/shared/types/domain'

export interface RequestOptions extends RequestInit {
  access_pin?: string
}

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

const DEMO_PINS: Record<string, AuthResponse> = {
  [import.meta.env.VITE_DEMO_USER_PIN ?? '202601']: {
    role: 'dispatcher',
    is_admin: false,
    access_pin_valid: true,
  },
  [import.meta.env.VITE_DEMO_ADMIN_PIN ?? '999999']: {
    role: 'admin',
    is_admin: true,
    access_pin_valid: true,
  },
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string
  readonly fields: Record<string, string[]>

  constructor(status: number, body: Partial<ValidationErrorBody>, fallbackMessage?: string) {
    super(body.detail || fallbackMessage || `Ошибка API ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code ?? 'http_error'
    this.detail = body.detail ?? fallbackMessage ?? `Ошибка API ${status}`
    this.fields = body.fields ?? {}
  }
}

async function parseErrorBody(response: Response): Promise<Partial<ValidationErrorBody>> {
  try {
    return (await response.json()) as Partial<ValidationErrorBody>
  } catch {
    return {}
  }
}

let unauthorizedHandler: (() => void) | null = null

/** Регистрирует реакцию приложения на истёкший или отозванный ключ доступа. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { access_pin, ...requestInit } = options
  const headers = new Headers(requestInit.headers)
  headers.set('Accept', 'application/json')
  if (access_pin) headers.set('X-Access-Pin', access_pin)
  if (requestInit.body !== undefined && !headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json')

  const response = await fetch(`${API_BASE}${path}`, { ...requestInit, headers })
  if (!response.ok) {
    // Ключ перестал подходить (отозван/изменён) — просим приложение вернуть вход.
    // Проверки самого ключа (/auth/*) разбираются со стором авторизации.
    if (response.status === 401 && !path.startsWith('/auth/')) unauthorizedHandler?.()
    throw new ApiError(response.status, await parseErrorBody(response))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function isMockFallbackEnabled(): boolean {
  return import.meta.env.DEV
}

function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError
}

/** 404/5xx считаем признаком «API ещё не поднят», 4xx — реальной ошибкой запроса. */
function isFallbackEligible(error: unknown): boolean {
  if (!isMockFallbackEnabled()) return false
  if (isNetworkError(error)) return true
  if (error instanceof ApiError) return error.status === 404 || error.status >= 500
  return false
}

async function requestWithFallback<T>(
  path: string,
  options: RequestOptions,
  fallback: () => T,
): Promise<Loaded<T>> {
  try {
    return { data: await request<T>(path, options), source: 'api' satisfies DataSource }
  } catch (error) {
    if (!isFallbackEligible(error)) throw error
    console.warn(`[api] ${path} недоступен, используются резервные данные`, error)
    return { data: clone(fallback()), source: 'mock' }
  }
}

/**
 * Проверка сохранённого ключа доступа на сервере.
 *
 * Без mock-fallback: смысл вызова в том, чтобы узнать мнение сервера,
 * а не подтвердить сам себя демо-ответом.
 */
export function fetchSession(accessPin: string): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/session', { access_pin: accessPin })
}

export async function verifyPin(accessPin: string): Promise<AuthResponse> {
  try {
    return await request<AuthResponse>('/auth/verify-pin', {
      method: 'POST',
      access_pin: accessPin,
    })
  } catch (error) {
    if (!isFallbackEligible(error)) throw error
    const demoSession = DEMO_PINS[accessPin]
    if (!demoSession)
      throw new ApiError(401, { code: 'unauthorized', detail: 'Неверный код доступа' })
    return clone(demoSession)
  }
}

export function fetchErpState(accessPin: string): Promise<Loaded<ERPState>> {
  return requestWithFallback<ERPState>(
    '/erp/state',
    { method: 'GET', access_pin: accessPin },
    () => mockData.mockErpState,
  )
}

/**
 * Мутации не имеют mock-fallback: логист обязан видеть реальный результат PATCH,
 * иначе изменение «сохранится» только в браузере и потеряется после перезагрузки.
 */
export function patchOrder(
  orderId: number,
  patch: ClientOrderPatch,
  accessPin: string,
): Promise<ClientOrder> {
  return request<ClientOrder>(`/erp/orders/${orderId}`, {
    method: 'PATCH',
    access_pin: accessPin,
    body: JSON.stringify(patch),
  })
}

export function patchProduct(
  productId: number,
  patch: ProductPatch,
  accessPin: string,
): Promise<Product> {
  return request<Product>(`/erp/products/${productId}`, {
    method: 'PATCH',
    access_pin: accessPin,
    body: JSON.stringify(patch),
  })
}

export function patchTruck(truckId: number, patch: TruckPatch, accessPin: string): Promise<Truck> {
  return request<Truck>(`/erp/trucks/${truckId}`, {
    method: 'PATCH',
    access_pin: accessPin,
    body: JSON.stringify(patch),
  })
}

export function patchStock(
  stockId: number,
  patch: WarehouseStockPatch,
  accessPin: string,
): Promise<WarehouseStock> {
  return request<WarehouseStock>(`/erp/stocks/${stockId}`, {
    method: 'PATCH',
    access_pin: accessPin,
    body: JSON.stringify(patch),
  })
}

/* --- Ручное создание: тоже мутации, поэтому тоже без mock-fallback --- */

export function createProduct(payload: ProductCreate, accessPin: string): Promise<Product> {
  return request<Product>('/erp/products', {
    method: 'POST',
    access_pin: accessPin,
    body: JSON.stringify(payload),
  })
}

export function createClient(payload: ClientCreate, accessPin: string): Promise<Client> {
  return request<Client>('/erp/clients', {
    method: 'POST',
    access_pin: accessPin,
    body: JSON.stringify(payload),
  })
}

export function createTruck(payload: TruckCreate, accessPin: string): Promise<Truck> {
  return request<Truck>('/erp/trucks', {
    method: 'POST',
    access_pin: accessPin,
    body: JSON.stringify(payload),
  })
}

export function createOrder(payload: ClientOrderCreate, accessPin: string): Promise<ClientOrder> {
  return request<ClientOrder>('/erp/orders', {
    method: 'POST',
    access_pin: accessPin,
    body: JSON.stringify(payload),
  })
}

export function createStock(
  payload: WarehouseStockCreate,
  accessPin: string,
): Promise<WarehouseStock> {
  return request<WarehouseStock>('/erp/stocks', {
    method: 'POST',
    access_pin: accessPin,
    body: JSON.stringify(payload),
  })
}

/**
 * Подбор оптимальной машины и маршрута для заявки («В работе»).
 * Без mock-fallback: назначение должно отражать реальные остатки и парк.
 */
export function assignOrder(orderId: number, accessPin: string): Promise<OrderAssignment> {
  return request<OrderAssignment>(`/erp/orders/${orderId}/assign`, {
    method: 'POST',
    access_pin: accessPin,
  })
}

export function fetchWeather(accessPin: string): Promise<Loaded<WeatherResponse>> {
  return requestWithFallback<WeatherResponse>(
    '/weather/current',
    { method: 'GET', access_pin: accessPin },
    () => mockData.mockWeather,
  )
}

/**
 * Мутация настроек погоды: без mock-fallback, иначе пресет «сохранится» только
 * в браузере, а сервер продолжит считать по старому режиму.
 */
export function overrideWeather(mode: WeatherMode, accessPin: string): Promise<WeatherResponse> {
  return request<WeatherResponse>('/weather/override', {
    method: 'POST',
    access_pin: accessPin,
    body: JSON.stringify({ mode }),
  })
}

/**
 * XLSX-маршрутный лист сохранённого прогона.
 *
 * Это файл, а не JSON, поэтому идём мимо общего `request`: он не умеет blob
 * и не читает `Content-Disposition`. Имя файла берём из ответа сервера.
 */
export async function downloadRouteSheet(
  runId: number,
  accessPin: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${API_BASE}/export/run/${runId}/xlsx`, {
    headers: { 'X-Access-Pin': accessPin, Accept: '*/*' },
  })
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get('Content-Disposition'), runId),
  }
}

/** `attachment; filename="agrologistix-run-7.xlsx"` → имя файла с fallback. */
function filenameFromDisposition(header: string | null, runId: number): string {
  const match = header?.match(/filename="?([^";]+)"?/i)
  const name = match?.[1]?.trim()
  return name && name.length > 0 ? name : `agrologistix-run-${runId}.xlsx`
}

/**
 * Расчёт плана: без mock-fallback — выдуманный план хуже явной ошибки,
 * потому что на его основе диспетчер принимает решения.
 */
export function optimize(accessPin: string): Promise<SolverResponse> {
  return request<SolverResponse>('/solver/optimize', {
    method: 'POST',
    access_pin: accessPin,
    body: JSON.stringify({}),
  })
}

/** Человекочитаемое сообщение об ошибке для v-alert. */
export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Код доступа не принят или сессия истекла.'
    if (error.status === 403) return 'Недостаточно прав для этого действия.'
    if (error.status === 404) return 'Данные не найдены — возможно, они уже обновлены.'
    if (error.status === 422) return `Некорректное значение: ${error.detail}`
    if (error.status >= 500)
      return 'Сервис временно недоступен. Изменение не сохранено — повторите позже.'
    return error.detail
  }
  if (error instanceof TypeError)
    return 'Нет связи с сервисом: изменение не сохранено. Проверьте подключение и повторите.'
  if (error instanceof Error) return error.message
  return 'Не удалось выполнить запрос. Попробуйте ещё раз.'
}
