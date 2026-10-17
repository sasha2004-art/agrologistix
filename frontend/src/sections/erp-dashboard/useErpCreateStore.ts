/**
 * Ручное создание справочников: библиотека товаров, магазины, машины, заявки, остатки.
 *
 * Отдельный стор, потому что «создать строку» и «изменить строку» — разные сценарии,
 * а тихий перезапрос состояния и уведомления уже живут в `useErpStore`.
 */

import { defineStore } from 'pinia'
import {
  createClient,
  createOrder,
  createProduct,
  createStock,
  createTruck,
} from '@/shared/api/httpClient'
import type {
  ClientCreate,
  ClientOrderCreate,
  ProductCreate,
  TruckCreate,
  WarehouseStockCreate,
} from '@/shared/types/domain'
import { useErpStore } from './useErpStore'

export const useErpCreateStore = defineStore('erpCreate', () => {
  const erp = useErpStore()

  function addProduct(payload: ProductCreate): Promise<boolean> {
    return erp.runMutation(
      'product:new',
      `Товар «${payload.name}» добавлен в библиотеку`,
      async (accessPin) => {
        await createProduct(payload, accessPin)
      },
    )
  }

  function addClient(payload: ClientCreate): Promise<boolean> {
    return erp.runMutation(
      'client:new',
      `Магазин «${payload.name}» добавлен`,
      async (accessPin) => {
        await createClient(payload, accessPin)
      },
    )
  }

  function addTruck(payload: TruckCreate): Promise<boolean> {
    return erp.runMutation(
      'truck:new',
      `Машина «${payload.name}» добавлена в автопарк`,
      async (accessPin) => {
        await createTruck(payload, accessPin)
      },
    )
  }

  function addOrder(payload: ClientOrderCreate): Promise<boolean> {
    const clientName = erp.clientById.get(payload.client_id)?.name ?? 'покупателя'
    return erp.runMutation(`order:new`, `Заказ для «${clientName}» создан`, async (accessPin) => {
      await createOrder(payload, accessPin)
    })
  }

  function addStock(payload: WarehouseStockCreate): Promise<boolean> {
    const warehouseName = erp.warehouseById.get(payload.warehouse_id)?.name ?? 'склада'
    return erp.runMutation(
      `stock:new`,
      `Остаток добавлен: «${warehouseName}»`,
      async (accessPin) => {
        await createStock(payload, accessPin)
      },
    )
  }

  return { addProduct, addClient, addTruck, addOrder, addStock }
})
