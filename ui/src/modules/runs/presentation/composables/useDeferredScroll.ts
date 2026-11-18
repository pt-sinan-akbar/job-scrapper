import { nextTick, onBeforeUnmount, watch, type WatchStopHandle } from 'vue'
import { scrollMotion } from '@/shared/utils/scrollMotion'

const USER_SCROLL_EVENTS = ['wheel', 'touchstart', 'keydown'] as const

export function useDeferredScroll(targetId: string, isReady: () => boolean): () => void {
  let stopWatch: WatchStopHandle | null = null

  function cancel(): void {
    stopWatch?.()
    stopWatch = null
    USER_SCROLL_EVENTS.forEach((type) => window.removeEventListener(type, cancel))
  }

  async function scrollToTarget(): Promise<void> {
    cancel()
    await nextTick()
    document.getElementById(targetId)?.scrollIntoView({ behavior: scrollMotion() })
  }

  function start(): void {
    if (isReady()) {
      void scrollToTarget()
      return
    }
    USER_SCROLL_EVENTS.forEach((type) =>
      window.addEventListener(type, cancel, { once: true, passive: true }),
    )
    stopWatch = watch(isReady, (ready) => {
      if (ready) {
        void scrollToTarget()
      }
    })
  }

  onBeforeUnmount(cancel)

  return start
}
