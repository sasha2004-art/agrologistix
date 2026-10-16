/**
 * Shared domain types — точка синхронизации с backend.
 *
 * Источник правды: `backend/app/schemas/*.py` (Pydantic, `extra="forbid"`).
 * Все поля идут в snake_case, enum-значения повторяют `backend/app/schemas/enums.py`.
 */

export type UserRole = 'dispatcher' | 'admin'
export type RoadType = 'asphalt' | 'dirt'
export type DeliveryStatus = 'pending' | 'delivered'
export type TruckStatus = 'active' | 'broken'
export type StopStatus = 'planned' | 'delivered'
export type WeatherMode = 'normal' | 'heatwave_35c' | 'heavy_rain'
export type SolverMode = 'baseline' | 'what_if'
export type WarningSeverity = 'info' | 'warning' | 'error'

/** auth_schemas.AuthResponse */
export interface AuthResponse {
  role: UserRole
  is_admin: boolean
  access_pin_valid: boolean
}

/** erp_schemas.WarehouseResponse */
export interface Warehouse {
  id: number
  name: string
  lat: number
  lon: number
  address: string
  is_active: boolean
}

/** erp_schemas.ProductResponse */
export interface Product {
  id: number
  name: string
  code: string
  base_spoilage_rate: number
  optimal_temp_c: number
  base_cost_rub: number
}

/** erp_schemas.WarehouseStockResponse */
export interface WarehouseStock {
  id: number
  warehouse_id: number
  product_id: number
  available_kg: number
  initial_freshness: number
}

/** erp_schemas.ClientResponse */
export interface Client {
  id: number
  name: string
  lat: number
  lon: number
  road_type: RoadType
  address: string
}

/** erp_schemas.ClientOrderResponse */
export interface ClientOrder {
  id: number
  client_id: number
  product_id: number
  requested_kg: number
  purchase_price_rub: number
  unmet_penalty_rub: number
  delivery_status: DeliveryStatus
}

/** erp_schemas.TruckResponse */
export interface Truck {
  id: number
  name: string
  plate_number: string
  warehouse_id: number
  capacity_kg: number
  cruise_speed_kmh: number
  cost_per_km_rub: number
  fixed_trip_cost_rub: number
  has_reefer: boolean
  can_use_dirt: boolean
  status: TruckStatus
}

/** erp_schemas.ERPStateResponse */
export interface ERPState {
  warehouses: Warehouse[]
  products: Product[]
  stocks: WarehouseStock[]
  clients: Client[]
  orders: ClientOrder[]
  trucks: Truck[]
}

/** erp_schemas.DemoResetResponse */
export interface DemoResetResponse {
  status: 'ok'
  warehouses: number
  products: number
  stocks: number
  clients: number
  orders: number
  trucks: number
  seeded: boolean
}

/** weather_schemas.WeatherOverrideRequest */
export interface WeatherOverrideRequest {
  mode: WeatherMode
}

/** weather_schemas.WeatherResponse */
export interface WeatherResponse {
  latitude: number
  longitude: number
  temperature_c: number
  precipitation_mm: number
  weather_code: number | null
  mode: WeatherMode
  fetched_at: string
}

/** solver_schemas.SolverRequest */
export interface SolverRequest {
  mode: SolverMode
  baseline_run_id?: number
}

/** solver_schemas.SolverWarning */
export interface SolverWarning {
  code: string
  message: string
  severity: WarningSeverity
  client_id?: number | null
  order_id?: number | null
}

/** solver_schemas.RouteStopResponse */
export interface RouteStop {
  order_id?: number | null
  truck_id: number
  warehouse_id: number
  client_id: number
  product_id: number
  sequence_order: number
  shipped_kg: number
  distance_km: number
  eta_minutes: number
  expected_freshness: number
  trip_leg_cost_rub: number
  stop_status: StopStatus
}

/** solver_schemas.RoutePoint */
export interface RoutePoint {
  lat: number
  lon: number
}

/** solver_schemas.RouteResponse */
export interface Route {
  truck_id: number
  truck_name: string
  warehouse_id: number
  total_distance_km: number
  total_duration_min: number
  total_cost_rub: number
  geometry: RoutePoint[]
  stops: RouteStop[]
}

/** solver_schemas.Metrics */
export interface Metrics {
  total_tco_rub: number
  total_trip_cost_rub: number
  total_spoilage_loss_rub: number
  total_unmet_penalty_rub: number
  expected_net_profit_rub: number
  avg_freshness_pct: number
  shipped_kg: number
  unmet_kg: number
}

/** solver_schemas.MetricDelta */
export interface MetricDelta {
  before: number
  after: number
  delta: number
  delta_pct: number | null
}

/** solver_schemas.ComparisonDelta */
export interface ComparisonDelta {
  total_tco_rub: MetricDelta
  total_trip_cost_rub: MetricDelta
  total_spoilage_loss_rub: MetricDelta
  total_unmet_penalty_rub: MetricDelta
  expected_net_profit_rub: MetricDelta
  avg_freshness_pct: MetricDelta
  shipped_kg: MetricDelta
  unmet_kg: MetricDelta
}

/** solver_schemas.SolverResponse */
export interface SolverResponse {
  run_id: number
  parent_run_id?: number | null
  routes: Route[]
  metrics: Metrics
  warnings: SolverWarning[]
  comparison?: ComparisonDelta | null
}

/** error_schemas.APIErrorResponse */
export interface ApiErrorBody {
  code: string
  detail: string
  request_id?: string | null
}

/** error_schemas.ValidationErrorResponse */
export interface ValidationErrorBody extends ApiErrorBody {
  fields: Record<string, string[]>
}

/** Откуда пришли данные: живой API или dev-mock (fallback). */
export type DataSource = 'api' | 'mock'

export interface Loaded<T> {
  data: T
  source: DataSource
}
