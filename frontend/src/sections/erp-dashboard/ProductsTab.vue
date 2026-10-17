<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Библиотека товаров</h2>
        <p class="tab-subtitle">
          Культуры с параметрами порчи: отсюда товары попадают в заказы и партии на складах.
        </p>
      </div>
      <div class="header-actions">
        <v-chip class="soft-chip" size="small" prepend-icon="mdi-sprout-outline">
          {{ erp.products.length }} товаров
        </v-chip>
        <v-btn
          variant="tonal"
          color="primary"
          size="small"
          prepend-icon="mdi-plus"
          @click="createOpen = true"
        >
          Товар
        </v-btn>
      </div>
    </header>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Загружаем библиотеку товаров…"
      empty-title="Товаров пока нет"
      empty-icon="mdi-sprout-outline"
      @retry="reload"
    >
      <v-table density="comfortable" class="excel-table">
        <thead>
          <tr>
            <th scope="col">Код</th>
            <th scope="col">Название</th>
            <th scope="col" class="text-right">Порча, доля/час</th>
            <th scope="col" class="text-right">Оптимальная t, °C</th>
            <th scope="col" class="text-right">Себестоимость, ₽/кг</th>
            <th scope="col" class="text-right">Партий на складах</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="product in erp.products" :key="product.id">
            <td class="mono">{{ product.code }}</td>
            <td>{{ product.name }}</td>
            <td class="text-right mono">{{ product.base_spoilage_rate.toFixed(3) }}</td>
            <td class="text-right mono">{{ product.optimal_temp_c.toFixed(1) }}</td>
            <td class="text-right mono">{{ formatPrice(product.base_cost_rub) }}</td>
            <td class="text-right mono">{{ stockCount(product.id) }}</td>
          </tr>
        </tbody>
      </v-table>
    </StatePanel>

    <CreateProductDialog v-model="createOpen" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import StatePanel from '@/shared/components/StatePanel.vue'
import CreateProductDialog from './create/CreateProductDialog.vue'
import { useErpStore } from './useErpStore'
import { formatPrice } from '@/shared/utils/format'

const erp = useErpStore()
const createOpen = ref(false)

/** Сколько партий этого товара уже лежит на складах — видно, чем товар занят. */
const stockByProduct = computed(() => {
  const counts = new Map<number, number>()
  for (const stock of erp.stocks) {
    counts.set(stock.product_id, (counts.get(stock.product_id) ?? 0) + 1)
  }
  return counts
})

function stockCount(productId: number): number {
  return stockByProduct.value.get(productId) ?? 0
}

function reload(): void {
  void erp.loadState({ force: true })
}
</script>

<style scoped lang="scss">
.header-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
