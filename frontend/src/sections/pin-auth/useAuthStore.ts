import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, fetchSession, verifyPin } from '@/shared/api/httpClient'
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
  /** Ключ подтверждён сервером в этой сессии приложения, а не только в sessionStorage. */
  const isVerified = ref(false)

  async function login(pin: string): Promise<boolean> {
    isVerifying.value = true
    try {
      const result = await verifyPin(pin)
      if (!result.access_pin_valid) return false
      role.value = result.role
      accessPin.value = pin
      isVerified.value = true
      writeSession({ role: result.role, accessPin: pin })
      return true
    } finally {
      isVerifying.value = false
    }
  }

  /**
   * Проверяет сохранённый ключ на сервере: дашборд открывается только тогда,
   * когда сервер подтвердил PIN.
   *
   * Сервер недоступен — не повод выкидывать диспетчера: пускаем с прежним
   * статусом, а экраны сами покажут ошибку загрузки. Отказ (401/403) — повод.
   */
  async function verifySession(): Promise<boolean> {
    const pin = accessPin.value
    if (!pin) return false
    if (isVerified.value) return true
    try {
      const result = await fetchSession(pin)
      role.value = result.role
      isVerified.value = true
      writeSession({ role: result.role, accessPin: pin })
      return true
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        logout()
        return false
      }
      return true
    }
  }

  function logout(): void {
    role.value = null
    accessPin.value = null
    isVerified.value = false
    writeSession(null)
  }

  return {
    role,
    accessPin,
    isAuthenticated,
    is_admin,
    isVerifying,
    isVerified,
    login,
    verifySession,
    logout,
  }
})
