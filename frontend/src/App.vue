<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  ChatDotRound,
  DataAnalysis,
  Plus,
  Promotion,
  Setting,
  TrendCharts,
  VideoPause,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { api } from './api/client'
import EmptyState from './components/chat/EmptyState.vue'
import MessageBubble from './components/chat/MessageBubble.vue'
import MarketDashboardDialog from './components/market/MarketDashboardDialog.vue'
import AISettingsDialog from './components/settings/AISettingsDialog.vue'
import MarketSettingsDialog from './components/settings/MarketSettingsDialog.vue'
import { useChatStream } from './composables/useChatStream'

const conversations = ref([])
const activeId = ref(null)
const messages = ref([])
const draft = ref('')
const loading = ref(true)
const initializing = ref(true)
const currentRunId = ref(null)
const toolStatus = ref(null)
const settingsVisible = ref(false)
const marketSettingsVisible = ref(false)
const marketDashboardVisible = ref(false)
const aiConfig = ref(null)
const marketConfig = ref(null)
const scroller = ref(null)
const { status, stage, connect } = useChatStream()
const ACTIVE_CONVERSATION_KEY = 'stockpilot.activeConversationId'

const isRunning = computed(() => ['submitting', 'connecting', 'streaming', 'reconnecting'].includes(status.value))
const stageText = computed(() => ({
  classifying: '正在理解问题',
  fetching_market_data: '正在查询行情数据',
  generating_answer: '正在组织回答',
  ai_planning: 'AI 正在制定研究计划',
  collecting_evidence: '正在按 AI 计划查询证据',
  ai_synthesizing: 'AI 正在综合行情、K 线与舆情',
}[stage.value] || '正在处理'))

function makeRequestId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
}

function saveActiveConversation(id) {
  try {
    if (id) localStorage.setItem(ACTIVE_CONVERSATION_KEY, id)
  } catch {
    // The conversation still works when browser storage is unavailable.
  }
}

function getSavedConversation() {
  try {
    return localStorage.getItem(ACTIVE_CONVERSATION_KEY)
  } catch {
    return null
  }
}

async function scrollToBottom(instant = false) {
  await nextTick()
  if (!scroller.value) return
  if (instant) scroller.value.style.scrollBehavior = 'auto'
  scroller.value.scrollTop = scroller.value.scrollHeight
  if (instant) scroller.value.style.removeProperty('scroll-behavior')
}

async function loadConversations() {
  conversations.value = await api.listConversations()
  if (!activeId.value && conversations.value.length) {
    const savedId = getSavedConversation()
    const initialId = conversations.value.some((item) => item.id === savedId)
      ? savedId
      : conversations.value[0].id
    await selectConversation(initialId, true)
  }
}

async function newConversation() {
  const conversation = await api.createConversation()
  conversations.value.unshift(conversation)
  activeId.value = conversation.id
  saveActiveConversation(conversation.id)
  messages.value = []
  draft.value = ''
}

async function selectConversation(id, instant = true) {
  if (isRunning.value) return
  activeId.value = id
  saveActiveConversation(id)
  messages.value = await api.listMessages(id)
  await scrollToBottom(instant)
}

async function sendMessage(preset) {
  const content = (typeof preset === 'string' ? preset : draft.value).trim()
  if (!content || isRunning.value) return
  if (!activeId.value) await newConversation()
  draft.value = ''
  toolStatus.value = null
  const userMessage = { id: makeRequestId(), role: 'user', content }
  const assistantMessage = { id: makeRequestId(), role: 'assistant', content: '', streaming: true }
  messages.value.push(userMessage, assistantMessage)
  status.value = 'submitting'
  await scrollToBottom()

  try {
    const run = await api.createRun(activeId.value, content, makeRequestId())
    currentRunId.value = run.run_id
    connect(run.events_url, {
      onDelta(chunk) {
        assistantMessage.content += chunk
        scrollToBottom()
      },
      onTool(data) {
        toolStatus.value = data
      },
      async onCompleted(data) {
        assistantMessage.id = data.message_id
        assistantMessage.streaming = false
        currentRunId.value = null
        await loadConversations()
      },
      onCancelled() {
        assistantMessage.streaming = false
        assistantMessage.content ||= '已停止生成。'
        currentRunId.value = null
      },
      onError(message) {
        assistantMessage.streaming = false
        assistantMessage.content ||= '暂时无法生成回答，请稍后重试。'
        currentRunId.value = null
        ElMessage.error(message)
      },
    })
  } catch (error) {
    status.value = 'failed'
    assistantMessage.streaming = false
    assistantMessage.content = '请求发送失败，请检查后端服务。'
    ElMessage.error(error.message)
  }
}

async function cancelRun() {
  if (currentRunId.value) await api.cancelRun(currentRunId.value)
}

function onComposerKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

onMounted(async () => {
  try {
    const [config, market] = await Promise.all([
      api.getAIConfig(),
      api.getMarketConfig(),
      loadConversations(),
    ])
    aiConfig.value = config
    marketConfig.value = market
  } catch (error) {
    ElMessage.error(`无法连接后端：${error.message}`)
  } finally {
    loading.value = false
    await scrollToBottom(true)
    initializing.value = false
  }
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="logo-row">
        <div class="brand-mark">SP</div>
        <div><strong>StockPilot</strong><small>股票智能客服Agent</small></div>
      </div>
      <el-button class="new-chat" :icon="Plus" @click="newConversation">新建对话</el-button>
      <p class="section-label">最近对话</p>
      <nav v-loading="loading" class="conversation-list" aria-label="最近对话">
        <button
          v-for="item in conversations"
          :key="item.id"
          type="button"
          :class="{ active: activeId === item.id }"
          @click="selectConversation(item.id)"
        >
          <el-icon><ChatDotRound /></el-icon><span>{{ item.title }}</span>
        </button>
      </nav>
      <div class="sidebar-note"><i /> {{ marketConfig?.enabled ? '多源行情模式' : 'Fake 数据模式' }}</div>
    </aside>

    <main class="main-panel">
      <header class="topbar">
        <div><span class="status-dot" /> Agent 在线</div>
        <div class="topbar-actions">
          <el-tag :type="aiConfig?.enabled ? 'success' : 'info'" effect="plain" round>
            {{ aiConfig?.enabled ? aiConfig.model : 'Fake 模式' }}
          </el-tag>
          <el-button :icon="TrendCharts" round @click="marketDashboardVisible = true">行情看板</el-button>
          <el-button
            :type="marketConfig?.enabled ? 'success' : 'default'"
            :icon="DataAnalysis"
            circle
            aria-label="行情设置"
            @click="marketSettingsVisible = true"
          />
          <el-button :icon="Setting" circle aria-label="AI 设置" @click="settingsVisible = true" />
        </div>
      </header>

      <div ref="scroller" class="message-area">
        <EmptyState v-if="!messages.length" @select="sendMessage" />
        <div v-else class="message-list">
          <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
          <div v-if="isRunning" class="run-status">
            <span class="pulse" /> {{ stageText }}
            <span v-if="toolStatus"> · {{ toolStatus.source }}</span>
          </div>
        </div>
      </div>

      <footer class="composer-panel">
        <div class="composer" :class="{ 'composer--active': draft }">
          <textarea
            v-model="draft"
            :disabled="initializing"
            rows="1"
            maxlength="4000"
            placeholder="输入股票名称、代码或你想了解的问题…"
            aria-label="消息输入框"
            @keydown="onComposerKeydown"
          />
          <el-button v-if="isRunning" class="send-button stop-button" circle :icon="VideoPause" @click="cancelRun" />
          <el-button v-else class="send-button" circle :icon="Promotion" :disabled="initializing || !draft.trim()" @click="sendMessage" />
        </div>
        <p>AI 可能出错，请核验关键行情与财务数据。Shift + Enter 换行</p>
      </footer>
    </main>
    <AISettingsDialog
      v-model="settingsVisible"
      @saved="aiConfig = $event"
    />
    <MarketSettingsDialog
      v-model="marketSettingsVisible"
      @saved="marketConfig = $event"
    />
    <MarketDashboardDialog v-model="marketDashboardVisible" />
    <div v-if="initializing" class="startup-overlay" role="status" aria-live="polite">
      <div class="startup-card">
        <div class="brand-mark brand-mark--loading">SP</div>
        <span class="startup-spinner" aria-hidden="true" />
        <p>正在恢复对话…</p>
      </div>
    </div>
  </div>
</template>
