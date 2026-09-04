import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'


afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API client', () => {
  it('creates a conversation with JSON payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 'conversation-1', title: '新会话' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await api.createConversation()

    expect(result.id).toBe('conversation-1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/conversations',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ title: '新会话' }) }),
    )
  })
})
