import { toKeywordKey } from '@/modules/scrapes/domain/entities/scrapeInput'
import { parseKeywords } from '@/shared/utils/parseKeywords'

export interface KeywordDraft {
  chips: string[]
  text: string
}

export function commitKeywordText(draft: KeywordDraft, maxChips: number): KeywordDraft {
  if (draft.text.trim() === '') {
    return draft
  }
  if (draft.chips.length >= maxChips) {
    return draft
  }
  return { chips: addKeywordChips(draft.chips, draft.text, maxChips), text: '' }
}

export function addKeywordChips(chips: string[], text: string, maxChips: number): string[] {
  let nextChips = [...chips]
  for (const keyword of parseKeywords(text)) {
    nextChips = addKeywordChip(nextChips, keyword, maxChips)
  }
  return nextChips
}

function addKeywordChip(chips: string[], keyword: string, maxChips: number): string[] {
  if (chips.length >= maxChips) {
    return chips
  }
  if (hasKeywordChip(chips, keyword)) {
    return chips
  }
  return [...chips, keyword]
}

function hasKeywordChip(chips: string[], keyword: string): boolean {
  const keywordKey = toKeywordKey(keyword)
  return chips.some((chip) => toKeywordKey(chip) === keywordKey)
}
