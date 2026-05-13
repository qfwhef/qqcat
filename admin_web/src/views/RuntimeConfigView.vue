<template>
  <div class="runtime-page">
    <div class="page-header runtime-header">
      <div>
        <div class="page-title">AI 运行配置</div>
        <div class="page-subtitle">
          管理模型、摘要策略、消息窗口和外部通知配置
          <span class="runtime-updated">最后同步：{{ lastUpdatedText }}</span>
        </div>
      </div>
      <div class="runtime-actions">
        <el-button :loading="loading" @click="loadData">刷新</el-button>
        <el-button :loading="testingAi" @click="testAiConnection">测试连接</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </div>
    </div>

    <div class="runtime-overview">
      <div class="runtime-overview-item">
        <span>默认回复率</span>
        <strong>{{ form.default_reply_rate }}%</strong>
      </div>
      <div class="runtime-overview-item">
        <span>最大历史条数</span>
        <strong>{{ form.max_history }}</strong>
      </div>
      <div class="runtime-overview-item">
        <span>工具调用</span>
        <div class="state-pill" :class="{ active: form.enable_tools }">
          <i class="state-dot" />
          <span>{{ toolStateText }}</span>
        </div>
        <small>允许模型访问已注册工具链路</small>
      </div>
      <div class="runtime-overview-item">
        <span>摘要范围</span>
        <div class="scope-toggle">
          <button
            type="button"
            class="scope-option"
            :class="{ active: form.summary_only_group }"
            @click="setSummaryScope(true)"
          >
            仅群聊
          </button>
          <button
            type="button"
            class="scope-option"
            :class="{ active: !form.summary_only_group }"
            @click="setSummaryScope(false)"
          >
            群聊+私聊
          </button>
        </div>
        <small>当前生效：{{ summaryScopeText }}</small>
      </div>
    </div>

    <el-form label-position="top" :model="form">
      <div class="runtime-layout">
        <el-card class="page-card runtime-panel connection-panel">
          <template #header>
            <div class="panel-title">模型与连接</div>
          </template>
          <div class="connection-banner">
            <div class="banner-title">
              <el-icon><Connection /></el-icon>
              <span>模型连接状态</span>
            </div>
            <div class="banner-status" :class="{ active: !!form.ai_base_url.trim() }">
              <i class="state-dot" />
              <span>{{ form.ai_base_url.trim() ? "连接地址已配置" : "待配置连接地址" }}</span>
            </div>
            <div v-if="aiTestResult" class="test-result" :class="{ ok: aiTestResult.ok }">
              <strong>{{ aiTestResult.ok ? "连接正常" : "连接失败" }}</strong>
              <span>{{ aiTestResult.message || aiTestResult.error || "-" }}</span>
              <small v-if="aiTestResult.latency_ms">耗时 {{ aiTestResult.latency_ms }} ms</small>
              <small v-if="aiTestResult.tools_supported !== null && aiTestResult.tools_supported !== undefined">
                工具参数：{{ aiTestResult.tools_supported ? "可用" : "不可用" }}
              </small>
            </div>
          </div>
          <el-form-item label="AI Base URL" class="connection-form-item">
            <el-input v-model="form.ai_base_url" placeholder="例如 http://127.0.0.1:8317/v1" />
          </el-form-item>
          <div class="model-grid">
            <el-form-item label="文本模型" class="connection-form-item">
              <el-input v-model="form.text_model" />
            </el-form-item>
            <el-form-item label="视觉模型" class="connection-form-item">
              <el-input v-model="form.vision_model" />
            </el-form-item>
            <el-form-item label="生图模型" class="connection-form-item">
              <el-input v-model="form.image_model" placeholder="例如 gpt-image-2" />
            </el-form-item>
          </div>
          <div class="fallback-head">
            <div class="fallback-head-item">
              <el-icon><MagicStick /></el-icon>
              <span>文本回滚候选：{{ fallbackTextCount }} 个</span>
            </div>
            <div class="fallback-head-item">
              <el-icon><CircleCheckFilled /></el-icon>
              <span>视觉回滚候选：{{ fallbackVisionCount }} 个</span>
            </div>
          </div>
          <div class="fallback-grid">
            <el-form-item label="文本回滚链" class="connection-form-item">
              <el-input
                v-model="textFallbackRaw"
                type="textarea"
                :rows="5"
                placeholder="每行一个模型，也支持逗号分隔"
              />
            </el-form-item>
            <el-form-item label="视觉回滚链" class="connection-form-item">
              <el-input
                v-model="visionFallbackRaw"
                type="textarea"
                :rows="5"
                placeholder="每行一个模型，也支持逗号分隔"
              />
            </el-form-item>
          </div>
          <el-form-item label="日志级别" class="connection-form-item">
            <el-select v-model="form.log_level" style="width: 100%">
              <el-option label="DEBUG" value="DEBUG" />
              <el-option label="INFO" value="INFO" />
              <el-option label="WARNING" value="WARNING" />
              <el-option label="ERROR" value="ERROR" />
            </el-select>
          </el-form-item>
        </el-card>

        <el-card class="page-card runtime-panel">
          <template #header>
            <div class="panel-title">对话与摘要策略</div>
          </template>
          <div class="runtime-metrics">
            <el-form-item label="默认回复率">
              <el-input-number v-model="form.default_reply_rate" :min="0" :max="100" />
            </el-form-item>
            <el-form-item label="最大历史条数">
              <el-input-number v-model="form.max_history" :min="1" :max="500" />
            </el-form-item>
            <el-form-item label="摘要触发条数">
              <el-input-number v-model="form.summary_trigger_rounds" :min="1" :max="2000" />
            </el-form-item>
            <el-form-item label="摘要保留最近消息数">
              <el-input-number v-model="form.summary_keep_recent_messages" :min="1" :max="500" />
            </el-form-item>
            <el-form-item label="摘要冷却秒数">
              <el-input-number v-model="form.summary_cooldown_seconds" :min="0" :max="86400" />
            </el-form-item>
            <el-form-item label="摘要最少新增消息数">
              <el-input-number v-model="form.summary_min_new_messages" :min="1" :max="500" />
            </el-form-item>
          </div>

          <div class="switch-section">
            <div class="switch-title">功能开关</div>
            <div class="switch-list">
              <div class="switch-row" :class="{ active: form.enable_tools }">
                <div>
                  <div class="switch-label">工具调用</div>
                  <div class="switch-help">允许模型调用已注册工具</div>
                </div>
                <el-switch v-model="form.enable_tools" />
              </div>
              <div class="switch-row" :class="{ active: form.enable_summary_memory }">
                <div>
                  <div class="switch-label">摘要记忆</div>
                  <div class="switch-help">自动压缩历史对话为摘要</div>
                </div>
                <el-switch v-model="form.enable_summary_memory" />
              </div>
              <div class="switch-row" :class="{ active: form.summary_only_group }">
                <div>
                  <div class="switch-label">摘要仅群聊</div>
                  <div class="switch-help">私聊不触发摘要生成</div>
                </div>
                <el-switch v-model="form.summary_only_group" />
              </div>
            </div>
          </div>
        </el-card>

        <el-card class="page-card runtime-panel runtime-panel-full">
          <template #header>
            <div class="panel-title">Minecraft 通知</div>
          </template>
          <el-form-item label="通知群白名单">
            <el-input
              v-model="minecraftNotifyGroupsRaw"
              type="textarea"
              :rows="4"
              placeholder="每行一个群号，也支持逗号分隔"
            />
          </el-form-item>
          <div class="panel-footnote">
            生效规则：仅在配置了重启通知并通过密钥校验时向这些群推送消息。
          </div>
        </el-card>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, Connection, MagicStick } from '@element-plus/icons-vue'

import { adminApi } from '../api/admin'

const loading = ref(false)
const saving = ref(false)
const testingAi = ref(false)
const textFallbackRaw = ref('')
const visionFallbackRaw = ref('')
const minecraftNotifyGroupsRaw = ref('')
const lastUpdatedAt = ref<Date | null>(null)
const aiTestResult = ref<any | null>(null)

const form = reactive({
  ai_base_url: '',
  text_model: '',
  vision_model: '',
  image_model: '',
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

const lastUpdatedText = computed(() => {
  if (!lastUpdatedAt.value) return "-"
  return lastUpdatedAt.value.toLocaleString("zh-CN", { hour12: false })
})

const toolStateText = computed(() => (form.enable_tools ? "工具调用已开启" : "工具调用已关闭"))
const summaryScopeText = computed(() => (form.summary_only_group ? "仅群聊" : "群聊 + 私聊"))
const fallbackTextCount = computed(() => parseLines(textFallbackRaw.value).length)
const fallbackVisionCount = computed(() => parseLines(visionFallbackRaw.value).length)

const setSummaryScope = (onlyGroup: boolean) => {
  form.summary_only_group = onlyGroup
}

const loadData = async () => {
  loading.value = true
  try {
    const data = await adminApi.getRuntimeConfig()
    form.ai_base_url = data.ai_base_url || ''
    form.text_model = data.text_model || ''
    form.vision_model = data.vision_model || ''
    form.image_model = data.image_model || ''
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
    textFallbackRaw.value = Array.isArray(data.text_model_fallback)
      ? data.text_model_fallback.join('\n')
      : ''
    visionFallbackRaw.value = Array.isArray(data.vision_model_fallback)
      ? data.vision_model_fallback.join('\n')
      : ''
    lastUpdatedAt.value = new Date()
  } finally {
    loading.value = false
  }
}

const save = async () => {
  saving.value = true
  try {
    await adminApi.updateRuntimeConfig({
      ...form,
      minecraft_notify_groups: parseLines(minecraftNotifyGroupsRaw.value)
        .map((item) => Number(item))
        .filter((item) => Number.isFinite(item) && item > 0),
      text_model_fallback: parseLines(textFallbackRaw.value),
      vision_model_fallback: parseLines(visionFallbackRaw.value),
    })
    ElMessage.success('运行配置已更新')
    await loadData()
  } finally {
    saving.value = false
  }
}

const testAiConnection = async () => {
  testingAi.value = true
  try {
    aiTestResult.value = await adminApi.testRuntimeAi({
      ai_base_url: form.ai_base_url,
      text_model: form.text_model,
      enable_tools: form.enable_tools,
    })
    if (aiTestResult.value?.ok) {
      ElMessage.success('模型连接正常')
    } else {
      ElMessage.warning(aiTestResult.value?.message || '模型连接失败')
    }
  } finally {
    testingAi.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.runtime-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.runtime-header {
  margin-bottom: 0;
}

.runtime-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.runtime-updated {
  margin-left: 8px;
  color: #475569;
  font-weight: 500;
}

.runtime-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.runtime-overview-item {
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  background: linear-gradient(160deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
  animation: cardLiftIn 380ms ease both;
}

.runtime-overview-item span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.runtime-overview-item strong {
  display: block;
  margin-top: 6px;
  color: #0f172a;
  font-size: 22px;
  line-height: 1;
}

.runtime-overview-item small {
  display: block;
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.state-pill {
  margin-top: 8px;
  height: 30px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid rgba(244, 63, 94, 0.25);
  background: rgba(244, 63, 94, 0.08);
  color: #be123c;
  transition: all 180ms ease;
}

.state-pill.active {
  border-color: rgba(22, 163, 74, 0.3);
  background: rgba(22, 163, 74, 0.1);
  color: #166534;
}

.state-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 0 currentColor;
  animation: pulseDot 1.8s ease-out infinite;
}

.scope-toggle {
  margin-top: 8px;
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  background: #e5e7eb;
}

.scope-option {
  border: none;
  min-width: 94px;
  height: 26px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 12px;
  color: #64748b;
  background: transparent;
  cursor: pointer;
  user-select: none;
  transition: all 180ms ease;
}

.scope-option.active {
  color: #0f172a;
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.14);
}

.runtime-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.runtime-panel {
  border-radius: 12px;
  animation: cardLiftIn 420ms ease both;
}

.runtime-panel-full {
  grid-column: 1 / -1;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.connection-banner {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 10px;
  background: #f8fafc;
  padding: 10px 12px;
  margin-bottom: 12px;
}

.banner-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: #475569;
  font-weight: 600;
}

.banner-status {
  margin-top: 8px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  color: #9f1239;
  background: rgba(244, 63, 94, 0.08);
  border: 1px solid rgba(244, 63, 94, 0.26);
  transition: all 180ms ease;
}

.banner-status.active {
  color: #166534;
  background: rgba(22, 163, 74, 0.1);
  border-color: rgba(22, 163, 74, 0.3);
}

.test-result {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(244, 63, 94, 0.24);
  background: rgba(244, 63, 94, 0.07);
  color: #9f1239;
  font-size: 12px;
}

.test-result.ok {
  border-color: rgba(22, 163, 74, 0.28);
  background: rgba(22, 163, 74, 0.08);
  color: #166534;
}

.test-result strong {
  color: inherit;
}

.test-result span {
  color: #334155;
}

.test-result small {
  color: #64748b;
}

.model-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}

.fallback-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}

.fallback-head {
  margin: 2px 0 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.fallback-head-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  color: #334155;
  background: #eef2ff;
  border: 1px solid rgba(99, 102, 241, 0.18);
}

.runtime-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 10px;
}

.switch-section {
  margin-top: 4px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.switch-title {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
}

.switch-list {
  display: grid;
  gap: 10px;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.2);
  transition: all 180ms ease;
}

.switch-row.active {
  border-color: rgba(var(--theme-primary-rgb), 0.36);
  background: linear-gradient(100deg, rgba(239, 246, 255, 0.8), rgba(232, 250, 245, 0.8));
}

.switch-label {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
}

.switch-help {
  color: #64748b;
  font-size: 12px;
  margin-top: 3px;
}

.panel-footnote {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.connection-panel :deep(.el-form-item__label) {
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.connection-form-item :deep(.el-input__wrapper),
.connection-form-item :deep(.el-select__wrapper),
.connection-form-item :deep(.el-textarea__inner) {
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
  transition: border-color 180ms ease, box-shadow 180ms ease, background 180ms ease;
}

.connection-form-item :deep(.el-textarea__inner) {
  line-height: 1.45;
  min-height: 108px;
}

.connection-form-item :deep(.el-input__wrapper.is-focus),
.connection-form-item :deep(.el-select__wrapper.is-focused),
.connection-form-item :deep(.el-textarea__inner:focus) {
  border-color: rgba(var(--theme-primary-rgb), 0.46);
  box-shadow: 0 0 0 3px rgba(var(--theme-primary-rgb), 0.14);
  background: #ffffff;
}

@keyframes pulseDot {
  0% {
    box-shadow: 0 0 0 0 rgba(15, 23, 42, 0.22);
  }
  70% {
    box-shadow: 0 0 0 7px rgba(15, 23, 42, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(15, 23, 42, 0);
  }
}

@keyframes cardLiftIn {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 1320px) {
  .runtime-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .runtime-layout {
    grid-template-columns: 1fr;
  }

  .runtime-panel-full {
    grid-column: auto;
  }

  .model-grid {
    grid-template-columns: 1fr;
  }

  .fallback-grid {
    grid-template-columns: 1fr;
  }
}
</style>
