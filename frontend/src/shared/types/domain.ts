export type UserRole = 'dispatcher' | 'admin'
export type RoadSurface = 'asphalt' | 'dirt'
export type DeliveryStatus = 'pending' | 'delivered'
export type WeatherPreset = 'normal' | 'heatwave_35c' | 'heavy_rain'

export interface AuthResponse {
  authenticated: boolean
  role: UserRole
  is_admin: boolean
  access_pin?: string
}

export interface Warehouse {
  warehouse_id: string
  name: string
  address: string
  latitude: number
  longitude: number
}

export interface Product {
  product_id: string
  name: string
  unit: 'kg'
  shelf_life_hours: number
}

export interface WarehouseStock {
  warehouse_id: string
  product_id: string
  quantity_kg: number
}

export interface Client {
  client_id: string
  name: string
  address: string
  latitude: number
  longitude: number
  road_surface: RoadSurface
}

export interface ClientOrder {
  order_id: string
  client_id: string
  product_id: string
  quantity_kg: number
  delivery_status: DeliveryStatus
  price_per_kg: number
}

export interface Truck {
  truck_id: string
  name: string
  capacity_kg: number
  has_reefer: boolean
  vehicle_type: 'van' | 'medium_truck' | 'heavy_truck'
  broken: boolean
}

export interface WeatherState {
  preset: WeatherPreset
  temperature_c: number
  precipitation_mm: number
  label: string
}

export interface Metrics {
  total_cost: number
  unmet_kg: number
  expected_freshness: number
  distance_km: number
  route_count: number
}

export interface ComparisonDelta {
  total_cost: number
  unmet_kg: number
  expected_freshness: number
  distance_km: number
}

export interface SolverRequest {
  mode: 'baseline' | 'what_if'
  baseline_run_id?: string
}

export interface SolverResponse {
  run_id: string
  metrics: Metrics
  comparison_delta?: ComparisonDelta
  routes: Array<{
    route_id: string
    truck_id: string
    order_ids: string[]
    distance_km: number
  }>
}
