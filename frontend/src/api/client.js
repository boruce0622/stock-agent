async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `请求失败（${response.status}）`)
  }
  return response.status === 204 ? null : response.json()
}

export const api = {
  getAIConfig: () => request('/api/v1/ai-config'),
  listAIProviders: () => request('/api/v1/ai-config/providers'),
  saveAIConfig: (config) =>
    request('/api/v1/ai-config', { method: 'PUT', body: JSON.stringify(config) }),
  testAIConfig: (config) =>
    request('/api/v1/ai-config/test', { method: 'POST', body: JSON.stringify(config) }),
  getMarketConfig: () => request('/api/v1/market-config'),
  saveMarketConfig: (config) =>
    request('/api/v1/market-config', { method: 'PUT', body: JSON.stringify(config) }),
  testMarketConfig: (config) =>
    request('/api/v1/market-config/test', { method: 'POST', body: JSON.stringify(config) }),
  getQuote: (symbol) => request(`/api/v1/market-data/quote/${symbol}`),
  resolveStock: (query) =>
    request(`/api/v1/market-data/resolve?q=${encodeURIComponent(query)}`),
  getKline: (symbol, limit = 60) =>
    request(`/api/v1/market-data/kline/${symbol}?period=daily&limit=${limit}`),
  getSentiment: (symbol, limit = 12) =>
    request(`/api/v1/market-data/sentiment/${symbol}?limit=${limit}`),
  listConversations: () => request('/api/v1/conversations'),
  createConversation: (title = '新会话') =>
    request('/api/v1/conversations', { method: 'POST', body: JSON.stringify({ title }) }),
  listMessages: (conversationId) =>
    request(`/api/v1/conversations/${conversationId}/messages`),
  createRun: (conversationId, message, clientRequestId) =>
    request(`/api/v1/conversations/${conversationId}/runs`, {
      method: 'POST',
      body: JSON.stringify({ message, client_request_id: clientRequestId }),
    }),
  cancelRun: (runId) => request(`/api/v1/runs/${runId}/cancel`, { method: 'POST' }),
}
