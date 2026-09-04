<script setup>
import { computed } from 'vue'
import { UserFilled } from '@element-plus/icons-vue'

import { getDisplayedMessageContent } from '../../utils/messageContent'

const props = defineProps({
  message: { type: Object, required: true },
})

const isUser = computed(() => props.message.role === 'user')
const displayedContent = computed(() => getDisplayedMessageContent(props.message))
</script>

<template>
  <article class="message-row" :class="{ 'message-row--user': isUser }">
    <div class="avatar" :class="{ 'avatar--user': isUser }" aria-hidden="true">
      <el-icon v-if="isUser"><UserFilled /></el-icon>
      <span v-else>SP</span>
    </div>
    <div class="message-wrap">
      <div class="message-meta">{{ isUser ? '你' : 'StockPilot' }}</div>
      <div class="message-bubble" :class="{ 'message-bubble--user': isUser }">
        {{ displayedContent }}<span v-if="message.streaming" class="cursor" />
      </div>
    </div>
  </article>
</template>
