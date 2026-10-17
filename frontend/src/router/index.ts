import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'

/**
 * В приложении только два экрана: вход и рабочий стол.
 *
 * Ни лендинга, ни других страниц нет: любой адрес, кроме дашборда, ведёт на
 * форму входа, а дашборд открывается только с подтверждённым ключом.
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/sections/pin-auth/PinLoginPage.vue'),
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/sections/erp-dashboard/DashboardLayout.vue'),
      meta: { requiresAuth: true },
    },
    { path: '/:pathMatch(.*)*', redirect: { name: 'login' } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.requiresAuth) {
    // Дашборд доступен только с ключом, который подтвердил сервер.
    if (!auth.isAuthenticated) return { name: 'login', query: { redirect: to.fullPath } }
    if (!(await auth.verifySession())) return { name: 'login', query: { redirect: to.fullPath } }
    return true
  }

  // Неавторизованные остаются на входе; авторизованных вход сразу пускает в работу.
  if (to.name === 'login' && auth.isAuthenticated && (await auth.verifySession())) {
    return { name: 'dashboard' }
  }

  return true
})

export default router
