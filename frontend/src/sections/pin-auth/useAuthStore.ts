import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { verifyPin } from '@/shared/api/httpClient'
import type { UserRole } from '@/shared/types/domain'

export const useAuthStore = defineStore('auth', () => {
  const role = ref<UserRole | null>(null)
  const accessPin = ref<string | null>(null)
  const isAuthenticated = computed(() => role.value !== null)
  const is_admin = computed(() => role.value === 'admin')
  const isVerifying = ref(false)

  async function login(pin: string): Promise<boolean> {
    isVerifying.value = true
    try {
      const result = await verifyPin(pin)
      if (!result.authenticated) return false
      role.value = result.role
      accessPin.value = pin
      return true
    } finally {
      isVerifying.value = false
    }
  }

  function logout(): void {
    role.value = null
    accessPin.value = null
  }

  return { role, accessPin, isAuthenticated, is_admin, isVerifying, login, logout }
})
