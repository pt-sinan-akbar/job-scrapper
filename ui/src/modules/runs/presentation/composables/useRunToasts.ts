import { watch } from 'vue'
import { toast } from 'vue-sonner'
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import {
  toDiscordStatusView,
  toRunEndView,
  type RunToastView,
} from '@/modules/runs/presentation/components/runStatus'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'

function showToast(view: RunToastView | null): void {
  if (view !== null) {
    toast[view.toastKind](view.label)
  }
}

function toastOn(
  source: () => RunRecord | null,
  toView: (record: RunRecord) => RunToastView | null,
): void {
  watch(source, (record) => showToast(record === null ? null : toView(record)))
}

export function useRunToasts(): void {
  const store = useRunStore()
  toastOn(() => store.runOutcome, toRunEndView)
  toastOn(() => store.discordOutcome, toDiscordStatusView)
  watch(
    () => store.runError,
    (error) => {
      if (error !== null) {
        toast.error(error.message)
      }
    },
  )
}
