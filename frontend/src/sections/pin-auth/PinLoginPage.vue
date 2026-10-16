<template>
  <main class="login-page">
    <VideoBackdrop />
    <RouterLink class="login-back" to="/" aria-label="Вернуться на главную"><v-icon icon="mdi-arrow-left" /> AgroLogistix</RouterLink>
    <section
      class="login-card liquid-glass"
      aria-labelledby="login-title"
      @click="focusPin"
    >
      <div class="login-mark"><v-icon icon="mdi-leaf" size="23" /></div>
      <p class="login-region">КАЛУГА · ОБНИНСК</p>
      <h1 id="login-title">Терминал логиста</h1>
      <p class="login-instruction">Введите персональный PIN-код</p>
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
      <p class="login-status" :class="{ 'login-status--error': hasError }" aria-live="polite">
        {{ statusMessage }}
      </p>
      <v-progress-linear v-if="auth.isVerifying" indeterminate color="primary" rounded height="2" />
      <span class="security-note"><v-icon icon="mdi-shield-lock-outline" size="14" /> Цифры PIN-кода не отображаются</span>
    </section>
    <p class="login-copyright">AGROLOGISTIX <span>·</span> SECURE DISPATCH ACCESS</p>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import PinDotsIndicator from './PinDotsIndicator.vue'
import VideoBackdrop from '@/shared/components/VideoBackdrop.vue'
import { useAuthStore } from './useAuthStore'

const auth = useAuthStore()
const router = useRouter()
const pin = ref('')
const hasError = ref(false)
const shaking = ref(false)
const pinInput = ref<HTMLInputElement | null>(null)
const statusMessage = computed(() => (hasError.value ? 'PIN-код не принят. Попробуйте ещё раз.' : ''))
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
.login-page { position: relative; z-index: 1; min-height: 100vh; display: grid; place-items: center; padding: 72px 18px; color: #f8fafc; }
.login-back { position: absolute; z-index: 1; top: 27px; left: max(24px, calc((100vw - 1180px) / 2)); display: inline-flex; align-items: center; gap: 9px; color: #e2e8f0; text-decoration: none; font-size: 14px; }
.login-card { width: min(100%, 430px); padding: 38px 32px 30px; border-radius: 20px; text-align: center; background: rgba(15,23,42,.72); box-shadow: 0 24px 80px rgba(0,0,0,.28), inset 0 1px 1px rgba(255,255,255,.11); }
.login-mark { display: grid; place-items: center; width: 44px; height: 44px; margin: 0 auto 19px; border-radius: 13px; color: #062219; background: #10b981; }
.login-region { margin: 0 0 9px; color: #a7f3d0; font: 9px var(--font-mono); letter-spacing: .14em; }
.login-card h1 { margin: 0; font-size: 27px; font-weight: 500; letter-spacing: -.02em; }
.login-instruction { margin: 9px 0 31px; color: #bdc9d8; font-size: 13px; }
.pin-input { position: absolute; width: 1px; height: 1px; opacity: .01; pointer-events: none; }
.login-status { min-height: 19px; margin: 18px 0 12px; color: #cbd5e1; font-size: 12px; }
.login-status--error { color: #fecaca; }
.security-note { display: inline-flex; align-items: center; gap: 6px; color: #a6b3c4; font-size: 10px; }
.login-copyright { position: absolute; bottom: 22px; margin: 0; color: #94a3b8; font: 8px var(--font-mono); letter-spacing: .1em; }
.login-copyright span { padding: 0 5px; color: #10b981; }
@media (max-width: 480px) { .login-card { padding: 32px 20px 26px; }.login-back { top: 18px; left: 18px; } }
</style>
