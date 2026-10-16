import * as mockData from './mockData'
import type { AuthResponse, SolverRequest, SolverResponse, UserRole } from '@/shared/types/domain'

export interface RequestOptions extends RequestInit {
  access_pin?: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const dispatcherPin = '202601'
const adminPin = '999999'

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { access_pin, ...requestInit } = options
  const headers = new Headers(requestInit.headers)
  if (access_pin) headers.set('X-Access-Pin', access_pin)
  if (requestInit.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  return fetch(`${API_BASE}${path}`, { ...requestInit, headers }).then(async (response) => {
    if (!response.ok) throw new Error(`API ${response.status}`)
    return (await response.json()) as T
  })
}

function canUseMock(error: unknown): boolean {
  if (!import.meta.env.DEV) return false
  if (error instanceof TypeError) return true
  return !(error instanceof Error) || /API (404|500|502|503|504)/.test(error.message)
}

async function requestWithFallback<T>(
  path: string,
  options: RequestOptions,
  fallback: () => T,
): Promise<T> {
  try {
    return await request<T>(path, options)
  } catch (error) {
    if (!canUseMock(error)) throw error
    return fallback()
  }
}

export interface MockSnapshot {
  warehouses: typeof mockData.warehouses
  products: typeof mockData.products
  warehouse_stocks: typeof mockData.warehouseStocks
  clients: typeof mockData.clients
  orders: typeof mockData.clientOrders
  trucks: typeof mockData.trucks
  weather: typeof mockData.weatherStates
}

export function getMockSnapshot(): MockSnapshot {
  return {
    warehouses: mockData.warehouses,
    products: mockData.products,
    warehouse_stocks: mockData.warehouseStocks,
    clients: mockData.clients,
    orders: mockData.clientOrders,
    trucks: mockData.trucks,
    weather: mockData.weatherStates,
  }
}

export async function loadSnapshot(accessPin: string): Promise<MockSnapshot> {
  return requestWithFallback<MockSnapshot>(
    '/erp/state',
    { method: 'GET', access_pin: accessPin },
    getMockSnapshot,
  )
}

export async function verifyPin(accessPin: string): Promise<AuthResponse> {
  return requestWithFallback<AuthResponse>(
    '/auth/verify-pin',
    {
      method: 'POST',
      access_pin: accessPin,
    },
    () => {
      const role: UserRole | null =
        accessPin === adminPin ? 'admin' : accessPin === dispatcherPin ? 'dispatcher' : null
      if (!role) throw new Error('Неверный PIN-код')
      return { role, is_admin: role === 'admin', access_pin_valid: true }
    },
  )
}

export async function optimize(requestBody: SolverRequest, accessPin: string): Promise<SolverResponse> {
  return requestWithFallback<SolverResponse>(
    '/solver/optimize',
    { method: 'POST', access_pin: accessPin, body: JSON.stringify(requestBody) },
    () => ({
      run_id: 'mock-run-obninsk-001',
      metrics: {
        total_cost: 148600,
        unmet_kg: 0,
        expected_freshness: 94.8,
        distance_km: 186,
        route_count: 3,
      },
      comparison_delta: {
        total_cost: -8200,
        unmet_kg: -240,
        expected_freshness: 3.4,
        distance_km: -28,
      },
      routes: [
        { route_id: 'route-01', truck_id: 'truck-01', order_ids: ['order-001', 'order-002'], distance_km: 74 },
        { route_id: 'route-02', truck_id: 'truck-02', order_ids: ['order-003'], distance_km: 52 },
        { route_id: 'route-03', truck_id: 'truck-03', order_ids: ['order-004', 'order-005'], distance_km: 60 },
      ],
    }),
  )
}
