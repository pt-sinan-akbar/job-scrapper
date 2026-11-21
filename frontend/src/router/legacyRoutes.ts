import type { RouteLocationRaw, RouteRecordRaw } from 'vue-router'

const SCRAPES_PATH = '/scrapes'
const LEGACY_SCRAPES_PATH = '/runs'

const LEGACY_HASH_TARGETS: Record<string, RouteLocationRaw> = {
  '#config': { path: SCRAPES_PATH, hash: '#config' },
  '#discord': { path: '/discord', hash: '' },
}

export const legacyRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: (to) => LEGACY_HASH_TARGETS[to.hash] ?? { path: SCRAPES_PATH, hash: '' },
  },
  {
    path: LEGACY_SCRAPES_PATH,
    redirect: (to) => ({ path: SCRAPES_PATH, hash: to.hash }),
  },
]
