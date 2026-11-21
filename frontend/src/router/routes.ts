import type { RouteRecordRaw } from 'vue-router'
import { authRoutes } from '@/modules/auth/routes'
import { configRoutes } from '@/modules/config/routes'
import { discordRoutes } from '@/modules/discord/routes'
import { scrapeRoutes } from '@/modules/scrapes/routes'
import { legacyRoutes } from '@/router/legacyRoutes'

export const routes: RouteRecordRaw[] = [
  ...legacyRoutes,
  ...authRoutes,
  ...scrapeRoutes,
  ...configRoutes,
  ...discordRoutes,
]
