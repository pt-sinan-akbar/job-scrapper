import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { DiscordSendResult } from '@/modules/discord/domain/entities/Discord'
import DiscordSendResults from '@/modules/discord/presentation/components/DiscordSendResults.vue'

const RESULT: DiscordSendResult = {
  sent: 1,
  failed: 1,
  results: [
    {
      index: 0,
      kind: 'file',
      title: 'jobs-2026-11-21.md',
      jobCount: 31,
      status: 'sent',
      messageId: '9',
      error: null,
    },
    {
      index: 1,
      kind: 'text',
      title: null,
      jobCount: 0,
      status: 'failed',
      messageId: null,
      error: 'Too long',
    },
  ],
}

describe('DiscordSendResults', () => {
  it('shows the sent and failed counts', () => {
    const wrapper = mount(DiscordSendResults, { props: { result: RESULT } })

    expect(wrapper.text()).toContain('Sent 1, 1 failed')
  })

  it('lists every message with its status', () => {
    const wrapper = mount(DiscordSendResults, { props: { result: RESULT } })
    const rows = wrapper.findAll('li')

    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('jobs-2026-11-21.md')
    expect(rows[0]!.get('[data-slot="badge"]').text()).toBe('Sent')
    expect(rows[0]!.get('[data-slot="badge"]').attributes('data-tone')).toBe('accent')
    expect(rows[1]!.get('[data-slot="badge"]').text()).toBe('Failed')
    expect(rows[1]!.get('[data-slot="badge"]').attributes('data-tone')).toBe('danger')
  })

  it('shows the reason a message failed', () => {
    const wrapper = mount(DiscordSendResults, { props: { result: RESULT } })

    expect(wrapper.findAll('li')[1]!.text()).toContain('Too long')
  })

  it('shows how many jobs a file holds and nothing for free text', () => {
    const wrapper = mount(DiscordSendResults, { props: { result: RESULT } })
    const rows = wrapper.findAll('li')

    expect(rows[0]!.get('[data-slot="discord-send-job-count"]').text()).toBe('31 jobs')
    expect(rows[1]!.find('[data-slot="discord-send-job-count"]').exists()).toBe(false)
  })

  it('names a file with no title Jobs file', () => {
    const wrapper = mount(DiscordSendResults, {
      props: {
        result: {
          sent: 1,
          failed: 0,
          results: [{ ...RESULT.results[0]!, title: null, jobCount: 1 }],
        },
      },
    })

    expect(wrapper.get('li').text()).toContain('Jobs file')
    expect(wrapper.get('[data-slot="discord-send-job-count"]').text()).toBe('1 job')
  })

  it('names a free text message Free text', () => {
    const wrapper = mount(DiscordSendResults, {
      props: {
        result: {
          sent: 1,
          failed: 0,
          results: [{ ...RESULT.results[1]!, status: 'sent', error: null }],
        },
      },
    })

    expect(wrapper.get('li').text()).toContain('Free text')
  })
})
