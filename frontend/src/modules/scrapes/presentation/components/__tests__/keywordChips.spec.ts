import { describe, expect, it } from 'vitest'
import {
  addKeywordChips,
  commitKeywordText,
} from '@/modules/scrapes/presentation/components/keywordChips'

describe('addKeywordChips', () => {
  it('adds each comma separated keyword, trimmed', () => {
    expect(addKeywordChips(['django'], ' vue ,  react ', 10)).toEqual(['django', 'vue', 'react'])
  })

  it('skips empty parts', () => {
    expect(addKeywordChips([], ', vue,,', 10)).toEqual(['vue'])
  })

  it('skips a keyword already there, ignoring case and spaces', () => {
    expect(addKeywordChips(['Django'], ' django , vue, VUE', 10)).toEqual(['Django', 'vue'])
  })

  it('stops at the chip limit', () => {
    expect(addKeywordChips(['django'], 'vue, react, go', 3)).toEqual(['django', 'vue', 'react'])
  })

  it('leaves the given chips untouched', () => {
    const chips = ['django']

    addKeywordChips(chips, 'vue', 10)

    expect(chips).toEqual(['django'])
  })
})

describe('commitKeywordText', () => {
  it('turns the text into chips and clears it', () => {
    expect(commitKeywordText({ chips: ['django'], text: 'vue' }, 10)).toEqual({
      chips: ['django', 'vue'],
      text: '',
    })
  })

  it('does nothing for blank text', () => {
    const draft = { chips: ['django'], text: '   ' }

    expect(commitKeywordText(draft, 10)).toEqual(draft)
  })

  it('clears a duplicate without adding it', () => {
    expect(commitKeywordText({ chips: ['django'], text: ' DJANGO ' }, 10)).toEqual({
      chips: ['django'],
      text: '',
    })
  })

  it('keeps the text when the chips are full', () => {
    const draft = { chips: ['django', 'vue'], text: 'react' }

    expect(commitKeywordText(draft, 2)).toEqual(draft)
  })
})
