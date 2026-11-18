import type { RouteLocationRaw, RouteRecordRaw } from 'vue-router'

const RUNS_PATH = '/runs'

const LEGACY_HASH_TARGETS: Record<string, RouteLocationRaw> = {
  '#config': { path: RUNS_PATH, hash: '#config' },
  '#discord': { path: '/discord', hash: '' },
}

export const legacyRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: (to) => LEGACY_HASH_TARGETS[to.hash] ?? { path: RUNS_PATH, hash: '' },
  },
]
