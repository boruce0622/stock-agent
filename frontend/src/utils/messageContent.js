export const ASSISTANT_END_MARKER =
  '以上内容仅用于信息与教育目的，不构成投资建议。市场有风险，请核验最新数据。'

export function getDisplayedMessageContent(message) {
  const content = String(message?.content || '')
  if (message?.role === 'user') return content

  const markerIndex = content.indexOf(ASSISTANT_END_MARKER)
  if (markerIndex < 0) return content
  return content.slice(0, markerIndex + ASSISTANT_END_MARKER.length)
}
