import { useRouter } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'

const LOGIN_PATH = '/login'

export function useSignOut(): () => Promise<void> {
  const auth = useAuthStore()
  const runs = useRunStore()
  const router = useRouter()

  return async () => {
    await auth.logout()
    runs.reset()
    await router.push(LOGIN_PATH)
  }
}
