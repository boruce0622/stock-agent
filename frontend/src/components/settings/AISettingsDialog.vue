<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { api } from '../../api/client'

const props = defineProps({ modelValue: { type: Boolean, required: true } })
const emit = defineEmits(['update:modelValue', 'saved'])

const loading = ref(false)
const testing = ref(false)
const saving = ref(false)
const savedKeyMask = ref('')
const providers = ref([])
const form = reactive({
  provider: 'openai',
  model: '',
  base_url: '',
  api_key: '',
  enabled: true,
})

function payload() {
  return {
    provider: form.provider,
    model: form.model.trim(),
    base_url: form.base_url.trim() || null,
    api_key: form.api_key || null,
    enabled: form.enabled,
  }
}

function onProviderChange(providerId) {
  const provider = providers.value.find((item) => item.id === providerId)
  if (!provider) return
  form.base_url = provider.base_url || ''
  form.model = provider.model_examples[0] || ''
}

function currentProvider() {
  return providers.value.find((item) => item.id === form.provider)
}

async function loadConfig() {
  loading.value = true
  try {
    const [config, catalog] = await Promise.all([api.getAIConfig(), api.listAIProviders()])
    providers.value = catalog
    form.provider = config.provider || 'openai'
    form.model = config.model || ''
    form.base_url = config.base_url || ''
    form.api_key = ''
    form.enabled = config.configured ? config.enabled : true
    savedKeyMask.value = config.api_key_masked || ''
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

async function testConnection() {
  if (!form.model.trim()) return ElMessage.warning('请填写模型名称')
  if (!form.api_key && !savedKeyMask.value) return ElMessage.warning('请填写 API Key')
  testing.value = true
  try {
    const result = await api.testAIConfig(payload())
    ElMessage.success(`连接成功，耗时 ${result.latency_ms} ms`)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    testing.value = false
  }
}

async function save() {
  if (!form.model.trim()) return ElMessage.warning('请填写模型名称')
  if (!form.api_key && !savedKeyMask.value) return ElMessage.warning('请填写 API Key')
  saving.value = true
  try {
    const config = await api.saveAIConfig(payload())
    savedKeyMask.value = config.api_key_masked || ''
    form.api_key = ''
    ElMessage.success('AI 配置已加密保存')
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
    title="AI 模型设置"
    width="min(540px, calc(100vw - 28px))"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="ai-settings">
      <el-alert
        title="API Key 将加密保存，页面不会再次返回明文。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="供应商">
          <el-select v-model="form.provider" class="full-width" @change="onProviderChange">
            <el-option
              v-for="provider in providers"
              :key="provider.id"
              :label="provider.name"
              :value="provider.id"
            />
          </el-select>
          <div v-if="currentProvider()?.description" class="field-help">
            {{ currentProvider().description }}
            <a
              v-if="currentProvider().docs_url"
              :href="currentProvider().docs_url"
              target="_blank"
              rel="noopener noreferrer"
            >查看官方文档</a>
          </div>
        </el-form-item>
        <el-form-item label="模型名称" required>
          <el-input
            v-model="form.model"
            :placeholder="currentProvider()?.model_examples?.length
              ? `例如：${currentProvider().model_examples.join('、')}`
              : '填写账号可用的模型 ID'"
          />
        </el-form-item>
        <el-form-item label="API Key" required>
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="savedKeyMask ? `已保存：${savedKeyMask}；留空则不修改` : '请输入 API Key'"
          />
        </el-form-item>
        <el-form-item label="Base URL（可选）">
          <el-input
            v-model="form.base_url"
            :disabled="form.provider === 'openai'"
            placeholder="OpenAI 官方接口请留空"
          />
          <div class="field-help">兼容服务填写 HTTPS 地址，本地服务可使用 localhost HTTP。</div>
        </el-form-item>
        <el-form-item label="启用模型">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
    </div>
    <template #footer>
      <el-button :loading="testing" @click="testConnection">测试连接</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ai-settings { min-height: 340px; }
.ai-settings .el-alert { margin-bottom: 20px; }
.full-width { width: 100%; }
.field-help { margin-top: 6px; color: #87908b; font-size: 12px; line-height: 1.5; }
</style>
