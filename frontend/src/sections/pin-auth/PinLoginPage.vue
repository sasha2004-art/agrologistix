<template>
  <v-main class="d-flex align-center justify-center pa-4">
    <v-card class="login-card soft-card" max-width="420" width="100%">
      <v-card-item class="text-center pt-6 pb-0">
        <v-icon icon="mdi-leaf" color="primary" size="26" />
        <v-card-title class="text-h6 mt-3">Терминал логиста</v-card-title>
        <v-card-subtitle class="mt-1">Введите 6-значный PIN-код диспетчера</v-card-subtitle>
      </v-card-item>

      <v-card-text class="text-center pt-6" @click="focusPin">
        <PinDotsIndicator :length="pin.length" :error="hasError" :shaking="shaking" />
        <input
          ref="pinInput"
          class="pin-input"
          type="password"
          inputmode="numeric"
          autocomplete="one-time-code"
          aria-label="Шестизначный PIN-код"
          maxlength="6"
          :value="pin"
          @input="onInput"
          @keydown="onKeydown"
        />
        <v-alert v-if="hasError" type="error" variant="tonal" density="compact" class="mt-5 text-left">
          PIN-код не принят. Попробуйте ещё раз.
        </v-alert>
        <div class="status-slot">
          <v-progress-linear v-if="auth.isVerifying" indeterminate color="primary" height="2" />
        </div>
        <p class="text-caption text-medium-emphasis mt-3 mb-0">Цифры PIN-кода не отображаются</p>
      </v-card-text>

      <v-card-actions class="justify-center pb-5">
        <v-btn to="/" variant="text" prepend-icon="mdi-arrow-left">На главную</v-btn>
      </v-card-actions>
    </v-card>
  </v-main>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import PinDotsIndicator from './PinDotsIndicator.vue'
import { useAuthStore } from './useAuthStore'

const auth = useAuthStore()
const router = useRouter()
const pin = ref('')
const hasError = ref(false)
const shaking = ref(false)
const pinInput = ref<HTMLInputElement | null>(null)
let clearTimer: number | undefined

onMounted(() => pinInput.value?.focus())

function focusPin(): void {
  pinInput.value?.focus()
}

function onInput(event: Event): void {
  const input = event.target as HTMLInputElement
  const digits = input.value.replace(/\D/g, '').slice(0, 6)
  pin.value = digits
  input.value = digits
  hasError.value = false
  if (digits.length === 6) void submitPin(digits)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Backspace') {
    pin.value = pin.value.slice(0, -1)
    if (pinInput.value) pinInput.value.value = pin.value
    hasError.value = false
    event.preventDefault()
  }
  if (/^\d$/.test(event.key) && pin.value.length >= 6) event.preventDefault()
}

async function submitPin(value: string): Promise<void> {
  hasError.value = false
  try {
    const accepted = await auth.login(value)
    if (!accepted) throw new Error('PIN не принят')
    await router.replace('/dashboard')
  } catch {
    hasError.value = true
    shaking.value = true
    window.setTimeout(() => (shaking.value = false), 300)
    window.clearTimeout(clearTimer)
    clearTimer = window.setTimeout(async () => {
      pin.value = ''
      if (pinInput.value) pinInput.value.value = ''
      hasError.value = false
      await nextTick()
      pinInput.value?.focus()
    }, 420)
  }
}
</script>

<style scoped lang="scss">
.login-card {
  padding-block: 4px;
}

.pin-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.status-slot {
  min-height: 4px;
  margin-top: 14px;
}
</style>
