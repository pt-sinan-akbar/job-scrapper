import { Play, Send } from '@lucide/vue'

import type { NavItem } from '@/shared/components/types'

export const navItems: NavItem[] = [
  { id: 'scrapes', label: 'Runs', icon: Play, to: '/scrapes' },
  { id: 'discord', label: 'Discord', icon: Send, to: '/discord' },
]
