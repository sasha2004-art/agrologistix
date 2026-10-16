<template>
  <div class="state-panel" :style="{ minHeight }">
    <template v-if="status === 'loading'">
      <div class="state-loading" role="status" aria-live="polite" :aria-busy="true">
        <v-skeleton-loader type="heading" class="state-skeleton" />
        <v-skeleton-loader
          v-for="row in skeletonRows"
          :key="row"
          type="list-item-two-line"
          class="state-skeleton"
        />
        <p class="text-body-2 text-medium-emphasis mb-0">{{ loadingText }}</p>
      </div>
    </template>

    <div v-else-if="status === 'error'" class="state-block neu-inset" role="alert">
      <v-alert type="error" variant="tonal" density="comfortable" class="mb-0">
        {{ errorText ?? 'Не удалось загрузить данные.' }}
      </v-alert>
      <v-btn
        v-if="retryable"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-refresh"
        class="mt-3"
        @click="emit('retry')"
      >
        Повторить
      </v-btn>
    </div>

    <div v-else-if="status === 'empty'" class="state-block neu-inset">
      <v-empty-state :icon="emptyIcon" :title="emptyTitle" :text="emptyText" size="compact" />
    </div>

    <slot v-else />
  </div>
</template>

<script setup lang="ts">
export type PanelStatus = 'loading' | 'empty' | 'error' | 'ready'

withDefaults(
  defineProps<{
    status: PanelStatus
    loadingText?: string
    emptyTitle?: string
    emptyText?: string
    emptyIcon?: string
    errorText?: string | null
    minHeight?: string
    skeletonRows?: number
    retryable?: boolean
  }>(),
  {
    loadingText: 'Загружаем данные…',
    emptyTitle: 'Данных пока нет',
    emptyText: 'Измените фильтры или запустите расчёт поставок.',
    emptyIcon: 'mdi-tray-remove',
    errorText: null,
    minHeight: '120px',
    skeletonRows: 3,
    retryable: true,
  },
)

const emit = defineEmits<{ retry: [] }>()
</script>

<style scoped lang="scss">
.state-panel {
  display: block;
}

.state-loading {
  display: grid;
  gap: 6px;
}

.state-skeleton {
  background: transparent !important;
  box-shadow: none !important;
}

.state-block {
  padding: 16px;
}

.state-block :deep(.v-empty-state) {
  padding: 8px 0;
}
</style>
