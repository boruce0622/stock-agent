import { describe, expect, it } from 'vitest'

import { ASSISTANT_END_MARKER, getDisplayedMessageContent } from './messageContent'

describe('getDisplayedMessageContent', () => {
  it('隐藏助手免责声明后的内部内容', () => {
    const content = `正文\n\n${ASSISTANT_END_MARKER}\n\n分析方式：内部调试信息`

    expect(getDisplayedMessageContent({ role: 'assistant', content })).toBe(
      `正文\n\n${ASSISTANT_END_MARKER}`,
    )
  })

  it('不截断用户消息', () => {
    const content = `请解释：${ASSISTANT_END_MARKER}后面的文字`

    expect(getDisplayedMessageContent({ role: 'user', content })).toBe(content)
  })
})
