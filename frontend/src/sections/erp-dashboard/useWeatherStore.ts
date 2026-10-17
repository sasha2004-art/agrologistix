/**
 * Погода для расчёта поставок (Day 5).
 *
 * Источник правды — сервер: активный пресет хранится в SQLite (`weather_override`)
 * и переживает перезапуск. После каждого override обязательно перечитываем
 * `GET /weather/current`, чтобы UI не расходился с состоянием расчёта.
 */

import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { describeApiError, fetchWeather, overrideWeather } from '@/shared/api/httpClient'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import { useNotificationStore } from '@/shared/stores/useNotificationStore'
import type { DataSource, WeatherMode, WeatherResponse } from '@/shared/types/domain'

export type WeatherStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface WeatherPresetOption {
  value: WeatherMode
  /** Короткая подпись для кнопки. */
  label: string
  /** Понятное название для меню и печати. */
  title: string
  icon: string
  hint: string
  /** true — ручная симуляция для примера, false — фактическая погода. */
  simulation: boolean
}

export const WEATHER_PRESETS: WeatherPresetOption[] = [
  {
    value: 'normal',
    label: 'Фактическая',
    title: 'Фактическая погода',
    icon: 'mdi-weather-partly-cloudy',
    hint: 'Данные Open-Meteo по Калужской области',
    simulation: false,
  },
  {
    value: 'heatwave_35c',
    label: 'Симуляция: жара',
    title: 'Симуляция: жара +35 °C',
    icon: 'mdi-weather-sunny-alert',
    hint: 'Пример для расчёта: ускоренная порча без рефрижератора',
    simulation: true,
  },
  {
    value: 'heavy_rain',
    label: 'Симуляция: дождь',
    title: 'Симуляция: сильный дождь',
    icon: 'mdi-weather-pouring',
    hint: 'Пример для расчёта: замедление на грунтовках и порча',
    simulation: true,
  },
]

export function weatherPreset(mode: WeatherMode): WeatherPresetOption {
  return WEATHER_PRESETS.find((preset) => preset.value === mode) ?? WEATHER_PRESETS[0]
}

/** Иконка MDI по WMO weather code (Open-Meteo). */
export function weatherIcon(code: number | null): string {
  if (code === null) return 'mdi-weather-cloudy'
  if (code === 0) return 'mdi-weather-sunny'
  if (code <= 3) return 'mdi-weather-partly-cloudy'
  if (code <= 48) return 'mdi-weather-fog'
  if (code <= 57) return 'mdi-weather-rainy'
  if (code <= 67) return 'mdi-weather-pouring'
  if (code <= 77) return 'mdi-weather-snowy'
  if (code <= 82) return 'mdi-weather-pouring'
  if (code <= 86) return 'mdi-weather-snowy-heavy'
  return 'mdi-weather-lightning'
}

export const useWeatherStore = defineStore('weather', () => {
  const auth = useAuthStore()
  const notifications = useNotificationStore()

  const weather = ref<WeatherResponse | null>(null)
  const status = ref<WeatherStatus>('idle')
  const errorMessage = ref<string | null>(null)
  const source = ref<DataSource>('api')
  const pendingMode = ref<WeatherMode | null>(null)

  const mode = computed<WeatherMode>(() => weather.value?.mode ?? 'normal')
  const preset = computed(() => weatherPreset(mode.value))
  /** Ручная симуляция влияет на расчёт, но не является прогнозом. */
  const isSimulation = computed(() => mode.value !== 'normal')
  const icon = computed(() => weatherIcon(weather.value?.weather_code ?? null))
  const isLoading = computed(() => status.value === 'loading')
  const isPending = computed(() => pendingMode.value !== null)
  const hasError = computed(() => status.value === 'error')

  async function load(options: { force?: boolean; silent?: boolean } = {}): Promise<void> {
    const accessPin = auth.accessPin
    if (!accessPin) return
    if (status.value === 'loading') return
    if (status.value === 'ready' && !options.force && !options.silent) return

    if (!options.silent) {
      status.value = 'loading'
      errorMessage.value = null
    }
    try {
      const result = await fetchWeather(accessPin)
      weather.value = result.data
      source.value = result.source
      status.value = 'ready'
    } catch (error) {
      const message = describeApiError(error)
      errorMessage.value = message
      status.value = 'error'
      notifications.push('error', message)
    }
  }

  async function setPreset(next: WeatherMode): Promise<boolean> {
    const accessPin = auth.accessPin
    if (!accessPin || isPending.value) return false
    if (next === mode.value) return true

    pendingMode.value = next
    try {
      weather.value = await overrideWeather(next, accessPin)
      const chosen = weatherPreset(next)
      notifications.push(
        'success',
        chosen.simulation
          ? `Включена симуляция погоды: ${chosen.title.replace('Симуляция: ', '')}`
          : 'Расчёт снова идёт по фактической погоде',
      )
      await load({ force: true, silent: true })
      return true
    } catch (error) {
      notifications.push('error', describeApiError(error))
      return false
    } finally {
      pendingMode.value = null
    }
  }

  function clear(): void {
    weather.value = null
    status.value = 'idle'
    errorMessage.value = null
    pendingMode.value = null
  }

  watch(
    () => auth.isAuthenticated,
    (isAuthenticated) => {
      if (!isAuthenticated) clear()
    },
  )

  return {
    weather,
    status,
    errorMessage,
    source,
    pendingMode,
    mode,
    preset,
    isSimulation,
    icon,
    isLoading,
    isPending,
    hasError,
    load,
    setPreset,
    clear,
  }
})
