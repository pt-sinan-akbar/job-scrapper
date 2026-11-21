import { useRouter } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { useScrapeStore } from '@/modules/scrapes/presentation/stores/useScrapeStore'

const LOGIN_PATH = '/login'

export function useSignOut(): () => Promise<void> {
  const auth = useAuthStore()
  const scrapes = useScrapeStore()
  const router = useRouter()

  return async () => {
    await auth.logout()
    scrapes.reset()
    await router.push(LOGIN_PATH)
  }
}
