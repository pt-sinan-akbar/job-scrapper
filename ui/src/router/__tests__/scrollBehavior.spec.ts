import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'

import { scrollBehavior } from '@/router/scrollBehavior'

function routeTo(hash: string): RouteLocationNormalized {
  return { hash } as RouteLocationNormalized
}

const FROM = routeTo('')

describe('scrollBehavior', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({ matches: false, media: query })),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('goes to the top on a tab click', () => {
    expect(scrollBehavior(routeTo(''), FROM, null)).toEqual({ top: 0 })
  })

  it('restores the saved position on back and forward', () => {
    expect(scrollBehavior(routeTo('#config'), FROM, { left: 0, top: 480 })).toEqual({
      left: 0,
      top: 480,
    })
  })

  it('scrolls to the hash target when it is on the page', () => {
    document.body.innerHTML = '<section id="config"></section>'

    expect(scrollBehavior(routeTo('#config'), FROM, null)).toEqual({
      el: '#config',
      behavior: 'smooth',
    })
  })

  it('goes to the top when the hash target is not there yet', () => {
    expect(scrollBehavior(routeTo('#config'), FROM, null)).toEqual({ top: 0 })
  })
})
