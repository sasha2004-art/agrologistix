import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { verifyPin } from '@/shared/api/httpClient'
import type { UserRole } from '@/shared/types/domain'

const SESSION_KEY = 'agrologistix-auth'
interface AuthSession {
  role: UserRole
  accessPin: string
}

function readSession(): AuthSession | null {
  try {
    const stored = sessionStorage.getItem(SESSION_KEY)
    if (!stored) return null
    const session = JSON.parse(stored) as Partial<AuthSession>
    const storedRole = session.role
    const storedPin = session.accessPin
    if (
      (storedRole !== 'admin' && storedRole !== 'dispatcher') ||
      typeof storedPin !== 'string' ||
      !/^\d{6}$/.test(storedPin)
    ) {
      return null
    }
    return { role: storedRole, accessPin: storedPin }
  } catch {
    return null
  }
}

function writeSession(session: AuthSession | null): void {
  if (!session) {
    sessionStorage.removeItem(SESSION_KEY)
    return
  }
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export const useAuthStore = defineStore('auth', () => {
  const session = readSession()
  const role = ref<UserRole | null>(session?.role ?? null)
  const accessPin = ref<string | null>(session?.accessPin ?? null)
  const isAuthenticated = computed(() => role.value !== null && accessPin.value !== null)
  const is_admin = computed(() => role.value === 'admin')
  const isVerifying = ref(false)

  async function login(pin: string): Promise<boolean> {
    isVerifying.value = true
    try {
      const result = await verifyPin(pin)
      if (!result.access_pin_valid) return false
      role.value = result.role
      accessPin.value = pin
      writeSession({ role: result.role, accessPin: pin })
      return true
    } finally {
      isVerifying.value = false
    }
  }

  function logout(): void {
    role.value = null
    accessPin.value = null
    writeSession(null)
  }

  return { role, accessPin, isAuthenticated, is_admin, isVerifying, login, logout }
})
