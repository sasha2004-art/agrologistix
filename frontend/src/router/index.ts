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
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) return { name: 'dashboard' }
  return true
})

export default router
