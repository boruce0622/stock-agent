<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { api } from '../../api/client'

const props = defineProps({ modelValue: { type: Boolean, required: true } })
const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const kline = ref(null)
const sentiment = ref(null)
const quote = ref(null)
const query = ref('')
const resolvedSymbol = ref('')
const resolvedName = ref('')
const resolvedBoard = ref('')
const resolvedExchange = ref('')
const stockName = computed(() => quote.value?.data?.name || resolvedName.value || kline.value?.name || resolvedSymbol.value)

const chart = computed(() => {
  const records = (kline.value?.records || []).filter((item) =>
    [item.open, item.close, item.high, item.low].every(Number.isFinite))
  const width = 840
  const height = 310
  const left = 54
  const right = 18
  const top = 18
  const priceBottom = 238
  const volumeTop = 255
  const bottom = 292
  if (!records.length) return { records: [], width, height }
  const highest = Math.max(...records.map((item) => item.high))
  const lowest = Math.min(...records.map((item) => item.low))
  const maxVolume = Math.max(...records.map((item) => item.volume || 0), 1)
  const range = highest - lowest || 1
  const step = (width - left - right) / records.length
  const y = (price) => top + ((highest - price) / range) * (priceBottom - top)
  return {
    width,
    height,
    highest,
    lowest,
    left,
    right,
    top,
    priceBottom,
    volumeTop,
    bottom,
    candles: records.map((item, index) => {
      const x = left + step * index + step / 2
      const rising = item.close >= item.open
      const openY = y(item.open)
      const closeY = y(item.close)
      return {
        ...item,
        x,
        rising,
        color: rising ? '#d74b4b' : '#15956f',
        highY: y(item.high),
        lowY: y(item.low),
        bodyY: Math.min(openY, closeY),
        bodyHeight: Math.max(Math.abs(openY - closeY), 1.5),
        bodyWidth: Math.max(Math.min(step * 0.62, 9), 2),
        volumeY: bottom - ((item.volume || 0) / maxVolume) * (bottom - volumeTop),
      }
    }),
    firstDate: records[0].time,
    middleDate: records[Math.floor(records.length / 2)].time,
    lastDate: records.at(-1).time,
    latest: records.at(-1),
  }
})

const overallMeta = computed(() => ({
  positive: { label: '偏正面', type: 'danger' },
  neutral: { label: '中性', type: 'info' },
  negative: { label: '偏负面', type: 'success' },
}[sentiment.value?.overall] || { label: '暂无', type: 'info' }))

function sentimentMeta(value) {
  return {
    positive: { label: '正面', type: 'danger' },
    neutral: { label: '中性', type: 'info' },
    negative: { label: '负面', type: 'success' },
  }[value]
}

async function loadDashboard() {
  if (!query.value.trim()) return
  loading.value = true
  try {
    const resolution = await api.resolveStock(query.value.trim())
    const selected = resolution.matches[0]
    resolvedSymbol.value = selected.symbol
    resolvedName.value = selected.name
    resolvedBoard.value = selected.board || ''
    resolvedExchange.value = selected.exchange_name || ''
    quote.value = null
    kline.value = null
    sentiment.value = null
    const [quoteResult, klineResult, sentimentResult] = await Promise.all([
      api.getQuote(selected.symbol),
      api.getKline(selected.symbol, 60),
      api.getSentiment(selected.symbol, 12),
    ])
    quote.value = quoteResult
    kline.value = klineResult
    sentiment.value = sentimentResult
  } catch (error) {
    ElMessage.error(`行情看板加载失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (opened) => opened && loadDashboard())
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="股票行情与舆情"
    width="min(1040px, calc(100vw - 28px))"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="market-dashboard">
      <div class="stock-search">
        <el-input v-model="query" placeholder="输入股票名称或代码，如：贵州茅台、600519" clearable @keyup.enter="loadDashboard" />
        <el-button type="primary" :loading="loading" @click="loadDashboard">查询</el-button>
        <div v-if="quote?.data" class="quote-strip">
          <strong>{{ stockName }}</strong><span>{{ resolvedSymbol }}</span>
          <el-tag v-if="resolvedBoard" size="small" effect="plain" :title="resolvedExchange">{{ resolvedBoard }}</el-tag>
          <b>{{ quote.data.price?.toFixed(2) }}</b>
          <em :class="{ down: quote.data.change_pct < 0 }">{{ quote.data.change_pct >= 0 ? '+' : '' }}{{ quote.data.change_pct?.toFixed(2) }}%</em>
        </div>
      </div>
      <section class="dashboard-card chart-card">
        <div class="card-heading">
          <div>
            <span class="eyebrow-label">{{ resolvedSymbol }} · 日 K</span>
            <h3>价格走势</h3>
          </div>
          <div v-if="chart.latest" class="latest-price">
            <strong>{{ chart.latest.close?.toFixed(2) }}</strong>
            <span>{{ chart.lastDate }}</span>
          </div>
        </div>
        <div v-if="chart.candles?.length" class="chart-wrap">
          <svg :viewBox="`0 0 ${chart.width} ${chart.height}`" role="img" :aria-label="`${stockName}日K线图`">
            <line v-for="index in 5" :key="`grid-${index}`" :x1="chart.left" :x2="chart.width - chart.right" :y1="chart.top + (index - 1) * 55" :y2="chart.top + (index - 1) * 55" class="grid-line" />
            <text x="4" :y="chart.top + 5" class="axis-text">{{ chart.highest.toFixed(2) }}</text>
            <text x="4" :y="chart.priceBottom" class="axis-text">{{ chart.lowest.toFixed(2) }}</text>
            <g v-for="candle in chart.candles" :key="candle.time">
              <title>{{ candle.time }} 开 {{ candle.open }} 高 {{ candle.high }} 低 {{ candle.low }} 收 {{ candle.close }}</title>
              <line :x1="candle.x" :x2="candle.x" :y1="candle.highY" :y2="candle.lowY" :stroke="candle.color" />
              <rect :x="candle.x - candle.bodyWidth / 2" :y="candle.bodyY" :width="candle.bodyWidth" :height="candle.bodyHeight" :fill="candle.rising ? candle.color : '#fff'" :stroke="candle.color" />
              <rect :x="candle.x - candle.bodyWidth / 2" :y="candle.volumeY" :width="candle.bodyWidth" :height="chart.bottom - candle.volumeY" :fill="candle.color" opacity=".32" />
            </g>
            <text :x="chart.left" y="307" class="axis-text">{{ chart.firstDate }}</text>
            <text x="420" y="307" text-anchor="middle" class="axis-text">{{ chart.middleDate }}</text>
            <text :x="chart.width - chart.right" y="307" text-anchor="end" class="axis-text">{{ chart.lastDate }}</text>
          </svg>
        </div>
        <el-empty v-else-if="!loading" description="暂无 K 线数据" :image-size="72" />
        <p class="source-note">来源：{{ kline?.source || '加载中' }} · 红涨绿跌 · 最近 60 个交易周期</p>
      </section>

      <section class="dashboard-card sentiment-card">
        <div class="card-heading">
          <div>
            <span class="eyebrow-label">PUBLIC OPINION</span>
            <h3>近期舆情</h3>
          </div>
          <el-tag :type="overallMeta.type" effect="light" round>{{ overallMeta.label }}</el-tag>
        </div>
        <div v-if="sentiment" class="sentiment-summary">
          <span>正面 {{ sentiment.counts.positive }}</span>
          <span>中性 {{ sentiment.counts.neutral }}</span>
          <span>负面 {{ sentiment.counts.negative }}</span>
        </div>
        <div class="news-list">
          <a v-for="item in sentiment?.items" :key="`${item.published_at}-${item.title}`" :href="item.url" target="_blank" rel="noopener noreferrer" class="news-item">
            <div><el-tag :type="sentimentMeta(item.sentiment).type" size="small" effect="plain">{{ sentimentMeta(item.sentiment).label }}</el-tag><time>{{ item.published_at }}</time></div>
            <strong>{{ item.title }}</strong>
            <small>{{ item.source }}</small>
          </a>
        </div>
        <p class="source-note">{{ sentiment?.method || '舆情仅作信息展示' }}</p>
      </section>
    </div>
  </el-dialog>
</template>

<style scoped>
.market-dashboard { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(300px, .85fr); gap: 16px; min-height: 510px; }
.stock-search { display: flex; grid-column: 1 / -1; align-items: center; gap: 10px; }
.stock-search .el-input { width: min(360px, 100%); }
.quote-strip { display: flex; align-items: baseline; gap: 9px; margin-left: auto; white-space: nowrap; }
.quote-strip span { color: #849089; font-size: 11px; }
.quote-strip b { margin-left: 8px; font: 600 21px Georgia, serif; }
.quote-strip em { color: #d74b4b; font-size: 12px; font-style: normal; }
.quote-strip em.down { color: #15956f; }
.dashboard-card { min-width: 0; padding: 20px; border: 1px solid #e1e6e1; border-radius: 16px; background: #fbfcfa; }
.card-heading { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; }
.card-heading h3 { margin: 4px 0 0; font: 500 24px Georgia, "Songti SC", serif; }
.eyebrow-label { color: #197052; font-size: 10px; font-weight: 800; letter-spacing: .14em; }
.latest-price { display: grid; text-align: right; }
.latest-price strong { color: #1a2b23; font: 600 26px Georgia, serif; }
.latest-price span, .source-note, time, .news-item small { color: #88928c; font-size: 11px; }
.chart-wrap { width: 100%; overflow: hidden; border-radius: 10px; background: white; }
svg { display: block; width: 100%; height: auto; }
.grid-line { stroke: #e9ede9; stroke-width: 1; }
.axis-text { fill: #8b958f; font-size: 9px; }
.source-note { margin: 12px 0 0; line-height: 1.6; }
.sentiment-summary { display: flex; gap: 10px; margin-bottom: 12px; color: #647069; font-size: 12px; }
.news-list { display: grid; max-height: 390px; overflow-y: auto; }
.news-item { display: grid; gap: 7px; padding: 12px 4px; border-bottom: 1px solid #e5e9e5; color: #26342d; text-decoration: none; }
.news-item:hover strong { color: #126b4b; }
.news-item div { display: flex; align-items: center; gap: 8px; }
.news-item strong { font-size: 13px; line-height: 1.5; }
@media (max-width: 820px) {
  .market-dashboard { grid-template-columns: 1fr; }
  .stock-search { flex-wrap: wrap; }
  .quote-strip { order: 2; width: 100%; margin-left: 0; }
}
</style>
