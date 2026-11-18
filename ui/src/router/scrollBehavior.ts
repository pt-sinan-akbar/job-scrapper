import type { RouterScrollBehavior } from 'vue-router'
import { scrollMotion } from '@/shared/utils/scrollMotion'

export const scrollBehavior: RouterScrollBehavior = (to, _from, savedPosition) => {
  if (savedPosition) {
    return savedPosition
  }
  if (to.hash && document.getElementById(to.hash.slice(1)) !== null) {
    return { el: to.hash, behavior: scrollMotion() }
  }
  return { top: 0 }
}
