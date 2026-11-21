import { vi } from 'vitest'

const VISIBLE_HEIGHT_PX = 60
const FULL_HEIGHT_PX = 180

export function stubClampedText(isClamped: boolean): void {
  vi.spyOn(Element.prototype, 'clientHeight', 'get').mockReturnValue(VISIBLE_HEIGHT_PX)
  vi.spyOn(Element.prototype, 'scrollHeight', 'get').mockReturnValue(
    isClamped ? FULL_HEIGHT_PX : VISIBLE_HEIGHT_PX,
  )
}
