<template>
  <v-menu location="bottom end" :close-on-content-click="true">
    <template #activator="{ props: menuProps }">
      <v-btn
        v-bind="menuProps"
        variant="tonal"
        color="primary"
        class="weather-trigger"
        :loading="weather.isLoading && !weather.weather"
        :aria-label="triggerLabel"
      >
        <v-progress-circular
          v-if="weather.isPending"
          indeterminate
          size="16"
          width="2"
          class="me-2"
        />
        <v-icon v-else :icon="weather.icon" class="me-1" />
        <span class="weather-temp mono">{{ temperatureText }}</span>
        <span class="weather-mode">{{ weather.preset.label }}</span>
      </v-btn>
    </template>

    <v-list density="comfortable" min-width="280">
      <v-list-subheader>Режим погоды для расчёта</v-list-subheader>
      <v-list-item
        v-for="option in presets"
        :key="option.value"
        :active="option.value === weather.mode"
        :disabled="weather.isPending || weather.isLoading"
        :aria-pressed="option.value === weather.mode"
        @click="select(option.value)"
      >
        <template #prepend>
          <v-icon :icon="option.icon" />
        </template>
        <v-list-item-title>{{ option.label }}</v-list-item-title>
        <v-list-item-subtitle>{{ option.hint }}</v-list-item-subtitle>
        <template #append>
          <v-icon v-if="option.value === weather.mode" icon="mdi-check" color="primary" />
        </template>
      </v-list-item>

      <v-divider class="my-2" />

      <v-list-item lines="two" density="compact">
        <v-list-item-title class="text-body-2">Текущие данные</v-list-item-title>
        <v-list-item-subtitle class="text-caption">{{ currentDetails }}</v-list-item-subtitle>
      </v-list-item>

      <v-list-item v-if="weather.hasError" density="compact" @click="retry">
        <template #prepend>
          <v-icon icon="mdi-refresh" color="error" />
        </template>
        <v-list-item-title class="text-body-2 text-error"
          >Повторить загрузку погоды</v-list-item-title
        >
      </v-list-item>
    </v-list>
  </v-menu>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { WEATHER_PRESETS, useWeatherStore } from './useWeatherStore'
import type { WeatherMode } from '@/shared/types/domain'

const weather = useWeatherStore()
const presets = WEATHER_PRESETS

const temperatureText = computed(() =>
  weather.weather ? `${Math.round(weather.weather.temperature_c)} °C` : '—',
)

const triggerLabel = computed(
  () => `Погода: ${weather.preset.label}, ${temperatureText.value}. Выбрать режим расчёта поставок`,
)

const currentDetails = computed(() => {
  if (weather.hasError) return 'Данные недоступны'
  if (!weather.weather) return 'Загружаем…'
  const parts = [`осадки ${weather.weather.precipitation_mm.toFixed(1)} мм`]
  if (weather.source === 'mock') parts.push('dev-mock')
  return parts.join(' · ')
})

onMounted(() => {
  void weather.load()
})

function select(mode: WeatherMode): void {
  void weather.setPreset(mode)
}

function retry(): void {
  void weather.load({ force: true })
}
</script>

<style scoped lang="scss">
.weather-trigger {
  text-transform: none;
}

.weather-temp {
  margin-inline-end: 8px;
}

.weather-mode {
  font-size: 12px;
}

@media (max-width: 959px) {
  .weather-mode {
    display: none;
  }
}
</style>
