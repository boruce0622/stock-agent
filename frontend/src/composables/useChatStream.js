import { onBeforeUnmount, ref } from 'vue'


export function useChatStream() {
  const status = ref('idle')
  const stage = ref('')
  let source = null

  const close = () => {
    source?.close()
    source = null
  }

  const connect = (url, handlers = {}) => {
    close()
    status.value = 'connecting'
    source = new EventSource(url)

    source.addEventListener('run.status', (event) => {
      const data = JSON.parse(event.data)
      status.value = data.status === 'running' ? 'streaming' : data.status
      stage.value = data.stage || ''
      handlers.onStatus?.(data)
    })
    source.addEventListener('tool.result', (event) => handlers.onTool?.(JSON.parse(event.data)))
    source.addEventListener('message.delta', (event) => {
      status.value = 'streaming'
      handlers.onDelta?.(JSON.parse(event.data).content)
    })
    source.addEventListener('message.completed', (event) => {
      status.value = 'completed'
      handlers.onCompleted?.(JSON.parse(event.data))
      close()
    })
    source.addEventListener('run.cancelled', () => {
      status.value = 'cancelled'
      handlers.onCancelled?.()
      close()
    })
    source.addEventListener('run.error', (event) => {
      status.value = 'failed'
      handlers.onError?.(JSON.parse(event.data).message)
      close()
    })
    source.onerror = () => {
      if (!['completed', 'cancelled', 'failed'].includes(status.value)) {
        status.value = 'reconnecting'
      }
    }
  }

  onBeforeUnmount(close)
  return { status, stage, connect, close }
}

