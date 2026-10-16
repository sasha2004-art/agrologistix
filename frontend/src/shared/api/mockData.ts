import type {
  Client,
  ClientOrder,
  Product,
  Truck,
  Warehouse,
  WarehouseStock,
  WeatherState,
} from '@/shared/types/domain'

export const warehouses: Warehouse[] = [
  {
    warehouse_id: 'wh-obninsk-north',
    name: 'Обнинск-Северный',
    address: 'Обнинск',
    latitude: 55.128,
    longitude: 36.612,
  },
  {
    warehouse_id: 'wh-detchino',
    name: 'Детчино-Агро',
    address: 'Детчино',
    latitude: 54.92,
    longitude: 36.31,
  },
]

export const products: Product[] = [
  { product_id: 'strawberry', name: 'Клубника', unit: 'kg', shelf_life_hours: 36 },
  { product_id: 'tomato', name: 'Томаты', unit: 'kg', shelf_life_hours: 120 },
  { product_id: 'cucumber', name: 'Огурцы', unit: 'kg', shelf_life_hours: 96 },
]

export const warehouseStocks: WarehouseStock[] = [
  { warehouse_id: 'wh-obninsk-north', product_id: 'strawberry', quantity_kg: 840 },
  { warehouse_id: 'wh-obninsk-north', product_id: 'tomato', quantity_kg: 1860 },
  { warehouse_id: 'wh-obninsk-north', product_id: 'cucumber', quantity_kg: 1120 },
  { warehouse_id: 'wh-detchino', product_id: 'strawberry', quantity_kg: 620 },
  { warehouse_id: 'wh-detchino', product_id: 'tomato', quantity_kg: 1440 },
  { warehouse_id: 'wh-detchino', product_id: 'cucumber', quantity_kg: 930 },
]

export const clients: Client[] = [
  {
    client_id: 'client-01',
    name: 'Обнинск Фреш Маркет',
    address: 'Обнинск',
    latitude: 55.095,
    longitude: 36.61,
    road_surface: 'asphalt',
  },
  {
    client_id: 'client-02',
    name: 'Калуга Ритейл',
    address: 'Калуга',
    latitude: 54.513,
    longitude: 36.261,
    road_surface: 'asphalt',
  },
  {
    client_id: 'client-03',
    name: 'Малоярославец Опт',
    address: 'Малоярославец',
    latitude: 55.012,
    longitude: 36.463,
    road_surface: 'dirt',
  },
  {
    client_id: 'client-04',
    name: 'Балабаново Фудсервис',
    address: 'Балабаново',
    latitude: 55.178,
    longitude: 36.657,
    road_surface: 'asphalt',
  },
  {
    client_id: 'client-05',
    name: 'Боровск Гастро',
    address: 'Боровск',
    latitude: 55.207,
    longitude: 36.492,
    road_surface: 'dirt',
  },
]

export const clientOrders: ClientOrder[] = clients.map((client, index) => ({
  order_id: `order-${String(index + 1).padStart(3, '0')}`,
  client_id: client.client_id,
  product_id: products[index % products.length].product_id,
  quantity_kg: 280 + index * 65,
  delivery_status: index === 0 ? 'delivered' : 'pending',
  price_per_kg: 185 + index * 12,
}))

export const trucks: Truck[] = [
  {
    truck_id: 'truck-01',
    name: 'Рефрижератор 01',
    capacity_kg: 1800,
    has_reefer: true,
    vehicle_type: 'medium_truck',
    broken: false,
  },
  {
    truck_id: 'truck-02',
    name: 'Фургон 02',
    capacity_kg: 900,
    has_reefer: false,
    vehicle_type: 'van',
    broken: false,
  },
  {
    truck_id: 'truck-03',
    name: 'Еврофура 03',
    capacity_kg: 8000,
    has_reefer: true,
    vehicle_type: 'heavy_truck',
    broken: false,
  },
]

export const weatherStates: Record<WeatherState['preset'], WeatherState> = {
  normal: { preset: 'normal', temperature_c: 19, precipitation_mm: 0, label: 'Нормальная погода' },
  heatwave_35c: {
    preset: 'heatwave_35c',
    temperature_c: 35,
    precipitation_mm: 0,
    label: 'Жара · 35°C',
  },
  heavy_rain: {
    preset: 'heavy_rain',
    temperature_c: 12,
    precipitation_mm: 18,
    label: 'Сильный дождь',
  },
}
