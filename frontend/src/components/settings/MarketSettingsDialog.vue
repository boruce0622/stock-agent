<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { api } from '../../api/client'

const props = defineProps({ modelValue: { type: Boolean, required: true } })
const emit = defineEmits(['update:modelValue', 'saved'])

const loading = ref(false)
const testing = ref(false)
const saving = ref(false)
const form = reactive({ provider: 'hybrid', enabled: true })

function payload() {
  return {
    provider: form.provider,
    enabled: form.enabled,
  }
}

async function loadConfig() {
  loading.value = true
  try {
    const config = await api.getMarketConfig()
    form.provider = 'hybrid'
    form.enabled = config.configured ? config.enabled : true
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

async function testConnection() {
  testing.value = true
  try {
    const result = await api.testMarketConfig(payload())
    ElMessage.success(`已获取 ${result.sample_symbol} 行情，耗时 ${result.latency_ms} ms`)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    testing.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const config = await api.saveMarketConfig(payload())
    ElMessage.success('混合行情设置已保存')
    emit('saved', config)
    emit('update:modelValue', false)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    saving.value = false
  }
}

watch(() => props.modelValue, (opened) => opened && loadConfig())
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="真实行情设置"
    width="min(540px, calc(100vw - 28px))"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="market-settings">
      <el-alert
        title="腾讯提供实时主源，新浪和 AKShare 自动降级，Baostock 校验历史日线。"
        type="success"
        :closable="false"
        show-icon
      />
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="行情供应商">
          <el-select v-model="form.provider" class="full-width">
            <el-option label="多源公网行情" value="hybrid" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用真实行情">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <div class="integrity-note">
        公网接口按域名实行全局限速，相邻请求至少间隔 1.2 秒，并配置超时和失败重试。
        实时源全部不可用时会退回 Baostock 最近交易日日线，并明确标记为延迟数据。
      </div>
    </div>
    <template #footer>
      <el-button :loading="testing" @click="testConnection">测试实时行情</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.market-settings { min-height: 300px; }
.market-settings .el-alert { margin-bottom: 20px; }
.full-width { width: 100%; }
.integrity-note { padding: 12px 14px; border-radius: 9px; color: #526159; background: #f1f6f2; font-size: 12px; line-height: 1.7; }
</style>
