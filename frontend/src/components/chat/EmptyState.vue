<script setup>
defineEmits(['select'])

const prompts = [
  '贵州茅台今天涨了多少？',
  '查询平安银行最新行情',
  '宁德时代今天表现怎么样？',
  '什么是市盈率？',
]
</script>

<template>
  <section class="empty-state">
    <div class="brand-mark brand-mark--large">SP</div>
    <p class="eyebrow">STOCK INTELLIGENCE</p>
    <h2>今天想了解哪只股票？</h2>
    <p class="empty-copy">查询行情、理解指标，所有数字都会说明数据时间与来源。</p>
    <div class="prompt-grid">
      <button v-for="prompt in prompts" :key="prompt" type="button" @click="$emit('select', prompt)">
        <span>{{ prompt }}</span><span aria-hidden="true">↗</span>
      </button>
    </div>
  </section>
</template>

