import { Play, Send } from '@lucide/vue'

import type { NavItem } from '@/shared/components/types'

export const navItems: NavItem[] = [
  { id: 'runs', label: 'Runs', icon: Play, to: '/runs' },
  { id: 'discord', label: 'Discord', icon: Send, to: '/discord' },
]
