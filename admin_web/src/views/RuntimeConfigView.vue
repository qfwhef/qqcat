<template>
  <div>
    <div class="page-header">
      <div class="page-title">AI 运行配置</div>
      <div>
        <el-button :loading="loading" @click="loadData">刷新</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </div>
    </div>

    <el-card class="page-card">
      <el-form label-position="top" :model="form">
        <div class="split-grid">
          <div>
            <el-form-item label="AI Base URL">
              <el-input v-model="form.ai_base_url" placeholder="例如 http://127.0.0.1:8317/v1" />
            </el-form-item>
            <el-form-item label="文本模型">
              <el-input v-model="form.text_model" />
            </el-form-item>
            <el-form-item label="视觉模型">
              <el-input v-model="form.vision_model" />
            </el-form-item>
            <el-form-item label="默认回复率">
              <el-input-number v-model="form.default_reply_rate" :min="0" :max="100" />
            </el-form-item>
            <el-form-item label="最大历史条数">
              <el-input-number v-model="form.max_history" :min="1" :max="500" />
            </el-form-item>
            <el-form-item label="Minecraft 通知群白名单">
              <el-input
                v-model="minecraftNotifyGroupsRaw"
                type="textarea"
                :rows="4"
                placeholder="每行一个群号，也支持逗号分隔"
              />
            </el-form-item>
            <el-form-item label="摘要触发条数">
              <el-input-number v-model="form.summary_trigger_rounds" :min="1" :max="2000" />
            </el-form-item>
            <el-form-item label="摘要保留最近消息数">
              <el-input-number v-model="form.summary_keep_recent_messages" :min="1" :max="500" />
            </el-form-item>
            <el-form-item label="日志级别">
              <el-select v-model="form.log_level" style="width: 100%">
                <el-option label="DEBUG" value="DEBUG" />
                <el-option label="INFO" value="INFO" />
                <el-option label="WARNING" value="WARNING" />
                <el-option label="ERROR" value="ERROR" />
              </el-select>
            </el-form-item>
          </div>

          <div>
            <el-form-item label="文本回滚链">
              <el-input
                v-model="textFallbackRaw"
                type="textarea"
                :rows="7"
                placeholder="每行一个模型，也支持逗号分隔"
              />
            </el-form-item>
            <el-form-item label="视觉回滚链">
              <el-input
                v-model="visionFallbackRaw"
                type="textarea"
                :rows="7"
                placeholder="每行一个模型，也支持逗号分隔"
              />
            </el-form-item>
            <el-form-item label="功能开关">
              <div style="display: grid; gap: 12px">
                <el-switch v-model="form.enable_tools" active-text="启用工具调用" />
                <el-switch v-model="form.enable_summary_memory" active-text="启用摘要记忆" />
                <el-switch v-model="form.summary_only_group" active-text="仅群聊启用摘要" />
              </div>
            </el-form-item>
            <el-form-item label="摘要冷却秒数">
              <el-input-number v-model="form.summary_cooldown_seconds" :min="0" :max="86400" />
            </el-form-item>
            <el-form-item label="摘要最少新增消息数">
              <el-input-number v-model="form.summary_min_new_messages" :min="1" :max="500" />
            </el-form-item>
          </div>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminApi } from '../api/admin'

const loading = ref(false)
const saving = ref(false)
const textFallbackRaw = ref('')
const visionFallbackRaw = ref('')
const minecraftNotifyGroupsRaw = ref('')
const form = reactive({
  ai_base_url: '',
  text_model: '',
  vision_model: '',
  default_reply_rate: 100,
  enable_tools: true,
  enable_summary_memory: true,
  summary_only_group: true,
  summary_trigger_rounds: 150,
  summary_keep_recent_messages: 16,
  summary_cooldown_seconds: 90,
  summary_min_new_messages: 12,
  max_history: 100,
  log_level: 'INFO',
})

const parseLines = (raw: string) =>
  raw
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)

const loadData = async () => {
  loading.value = true
  try {
    const data = await adminApi.getRuntimeConfig()
    form.ai_base_url = data.ai_base_url || ''
    form.text_model = data.text_model || ''
    form.vision_model = data.vision_model || ''
    form.default_reply_rate = Number(data.default_reply_rate ?? 100)
    form.enable_tools = Boolean(data.enable_tools)
    form.enable_summary_memory = Boolean(data.enable_summary_memory)
    form.summary_only_group = Boolean(data.summary_only_group)
    form.summary_trigger_rounds = Number(data.summary_trigger_rounds ?? 150)
    form.summary_keep_recent_messages = Number(data.summary_keep_recent_messages ?? 16)
    form.summary_cooldown_seconds = Number(data.summary_cooldown_seconds ?? 90)
    form.summary_min_new_messages = Number(data.summary_min_new_messages ?? 12)
    form.max_history = Number(data.max_history ?? 100)
    form.log_level = data.log_level ?? 'INFO'
    minecraftNotifyGroupsRaw.value = Array.isArray(data.minecraft_notify_groups)
      ? data.minecraft_notify_groups.join('\n')
      : ''
    textFallbackRaw.value = Array.isArray(data.text_model_fallback) ? data.text_model_fallback.join('\n') : ''
    visionFallbackRaw.value = Array.isArray(data.vision_model_fallback)
      ? data.vision_model_fallback.join('\n')
      : ''
  } finally {
    loading.value = false
  }
}

const save = async () => {
  saving.value = true
  try {
    await adminApi.updateRuntimeConfig({
      ...form,
      minecraft_notify_groups: parseLines(minecraftNotifyGroupsRaw.value).map((item) => Number(item)).filter((item) => Number.isFinite(item) && item > 0),
      text_model_fallback: parseLines(textFallbackRaw.value),
      vision_model_fallback: parseLines(visionFallbackRaw.value),
    })
    ElMessage.success('运行配置已更新')
    await loadData()
  } finally {
    saving.value = false
  }
}

loadData()
</script>
