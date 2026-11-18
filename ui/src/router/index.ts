import { createRouter, createWebHistory } from 'vue-router'
import { createAuthGuard } from '@/router/authGuard'
import { installPageTitle } from '@/router/pageTitle'
import { routes } from '@/router/routes'
import { scrollBehavior } from '@/router/scrollBehavior'

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior,
})

router.beforeEach(createAuthGuard())
installPageTitle(router)

export default router
