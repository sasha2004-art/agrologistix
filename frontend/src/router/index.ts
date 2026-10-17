import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'landing', component: () => import('@/sections/landing/LandingPage.vue') },
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
    // Любой неизвестный адрес ведёт на форму входа, а не в пустоту.
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

  if (to.name === 'login' && auth.isAuthenticated && (await auth.verifySession())) {
    return { name: 'dashboard' }
  }

  return true
})

export default router
