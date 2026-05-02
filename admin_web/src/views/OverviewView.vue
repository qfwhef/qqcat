<template>
  <div class="overview-page">
    <div class="page-header overview-header">
      <div>
        <div class="page-title">系统概览</div>
        <div class="page-subtitle">
          统一查看近 24 小时运行状态、模型配置和变更轨迹
          <span class="overview-updated">最后更新：{{ lastUpdatedText }}</span>
        </div>
      </div>
      <div class="overview-actions">
        <el-tag :type="healthTagType" effect="dark">{{ healthTagText }}</el-tag>
        <el-button :loading="loading" @click="loadData">刷新概览</el-button>
      </div>
    </div>

    <div class="overview-kpi-grid">
      <div
        v-for="metric in metricCards"
        :key="metric.key"
        class="overview-kpi-card"
      >
        <div class="overview-kpi-top">
          <div class="overview-kpi-label">{{ metric.label }}</div>
          <el-icon class="overview-kpi-icon"><component :is="metric.icon" /></el-icon>
        </div>
        <div class="overview-kpi-value">{{ metric.value }}</div>
        <div class="overview-kpi-foot">
          <el-tag size="small" :type="metric.tagType">{{ metric.tagText }}</el-tag>
          <span>{{ metric.hint }}</span>
        </div>
      </div>
    </div>

    <div class="overview-main-grid">
      <el-card class="page-card">
        <template #header>
          <div class="overview-card-header">
            <span>运行配置快照</span>
            <el-tag size="small" type="info">{{ runtimeModeText }}</el-tag>
          </div>
        </template>
        <div class="overview-config-grid">
          <div class="overview-config-item">
            <span>AI Base URL</span>
            <code>{{ runtimeConfig.ai_base_url || "-" }}</code>
          </div>
          <div class="overview-config-item">
            <span>文本模型</span>
            <code>{{ runtimeConfig.text_model || "-" }}</code>
          </div>
          <div class="overview-config-item">
            <span>视觉模型</span>
            <code>{{ runtimeConfig.vision_model || "-" }}</code>
          </div>
          <div class="overview-config-item">
            <span>文本回滚链</span>
            <code>{{ formatList(runtimeConfig.text_model_fallback) }}</code>
          </div>
          <div class="overview-config-item">
            <span>视觉回滚链</span>
            <code>{{ formatList(runtimeConfig.vision_model_fallback) }}</code>
          </div>
          <div class="overview-config-inline">
            <div class="inline-metric">
              <span>默认回复率</span>
              <strong>{{ runtimeConfig.default_reply_rate ?? "-" }}%</strong>
            </div>
            <div class="inline-metric">
              <span>最大历史条数</span>
              <strong>{{ runtimeConfig.max_history ?? "-" }}</strong>
            </div>
            <div class="inline-metric">
              <span>日志级别</span>
              <strong>{{ runtimeConfig.log_level || "-" }}</strong>
            </div>
          </div>
          <div class="overview-switches">
            <el-tag :type="runtimeConfig.enable_tools ? 'success' : 'warning'">
              工具调用：{{ runtimeConfig.enable_tools ? "开启" : "关闭" }}
            </el-tag>
            <el-tag :type="runtimeConfig.enable_summary_memory ? 'success' : 'warning'">
              摘要记忆：{{ runtimeConfig.enable_summary_memory ? "开启" : "关闭" }}
            </el-tag>
            <el-tag :type="runtimeConfig.summary_only_group ? 'info' : 'success'">
              摘要范围：{{ runtimeConfig.summary_only_group ? "仅群聊" : "群聊+私聊" }}
            </el-tag>
          </div>
        </div>
      </el-card>

      <el-card class="page-card">
        <template #header>
          <div class="overview-card-header">
            <span>最近失败 AI 调用</span>
            <el-tag size="small" :type="failureCountTagType">
              {{ stats.ai_failures_24h }} 次 / 24h
            </el-tag>
          </div>
        </template>
        <el-table :data="overview?.recent_failures || []" height="420" empty-text="暂无失败记录">
          <el-table-column prop="created_at" label="时间" min-width="160" />
          <el-table-column prop="session_type" label="会话" width="90" />
          <el-table-column prop="session_id" label="会话ID" min-width="110" />
          <el-table-column prop="stage" label="阶段" min-width="110" />
          <el-table-column prop="model_name" label="模型" min-width="170" />
          <el-table-column label="失败原因" min-width="120">
            <template #default="{ row }">
              <el-tag size="small" type="danger">{{ row.failure_reason || "unknown" }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-card class="page-card overview-change-card">
      <template #header>
        <div class="overview-card-header">
          <span>最近配置变更</span>
          <el-tag size="small" type="info">{{ (overview?.recent_config_changes || []).length }} 条</el-tag>
        </div>
      </template>
      <el-table :data="overview?.recent_config_changes || []" empty-text="暂无配置变更">
        <el-table-column prop="created_at" label="时间" min-width="160" />
        <el-table-column prop="config_domain" label="配置域" min-width="140" />
        <el-table-column prop="scope_ref" label="作用域" min-width="160" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="changeTypeTag(row.change_type)">
              {{ row.change_type || "-" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="changed_by" label="操作人" min-width="140" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Connection, Cpu, DataAnalysis, WarningFilled } from '@element-plus/icons-vue'

import { adminApi } from '../api/admin'

const loading = ref(false)
const overview = ref<any>(null)
const lastUpdatedAt = ref<Date | null>(null)

const runtimeConfig = computed(() => overview.value?.runtime_config || {})
const stats = computed(() => ({
  messages_24h: Number(overview.value?.stats?.messages_24h || 0),
  summaries_24h: Number(overview.value?.stats?.summaries_24h || 0),
  tool_messages_24h: Number(overview.value?.stats?.tool_messages_24h || 0),
  ai_failures_24h: Number(overview.value?.stats?.ai_failures_24h || 0),
}))

const successRate = computed(() => {
  const total = stats.value.messages_24h
  if (total <= 0) {
    return 100
  }
  const failed = Math.min(stats.value.ai_failures_24h, total)
  return Math.max(0, Math.round(((total - failed) / total) * 100))
})

const healthTagText = computed(() => {
  if (stats.value.ai_failures_24h >= 20) return "高风险"
  if (stats.value.ai_failures_24h >= 6) return "需要关注"
  return "运行稳定"
})

const healthTagType = computed(() => {
  if (stats.value.ai_failures_24h >= 20) return "danger"
  if (stats.value.ai_failures_24h >= 6) return "warning"
  return "success"
})

const failureCountTagType = computed(() => {
  if (stats.value.ai_failures_24h >= 20) return "danger"
  if (stats.value.ai_failures_24h >= 6) return "warning"
  return "success"
})

const runtimeModeText = computed(() => {
  const toolsEnabled = runtimeConfig.value.enable_tools ? "工具开启" : "工具关闭"
  const summaryEnabled = runtimeConfig.value.enable_summary_memory ? "摘要开启" : "摘要关闭"
  return `${toolsEnabled} / ${summaryEnabled}`
})

const metricCards = computed(() => [
  {
    key: "messages",
    label: "24h 消息数",
    value: stats.value.messages_24h.toLocaleString(),
    hint: "群聊与私聊总量",
    icon: DataAnalysis,
    tagText: stats.value.messages_24h >= 1000 ? "高活跃" : "常规",
    tagType: stats.value.messages_24h >= 1000 ? "success" : "info",
  },
  {
    key: "summaries",
    label: "24h 摘要数",
    value: stats.value.summaries_24h.toLocaleString(),
    hint: "记忆压缩产出",
    icon: Cpu,
    tagText: stats.value.summaries_24h > 0 ? "已产出" : "无产出",
    tagType: stats.value.summaries_24h > 0 ? "success" : "warning",
  },
  {
    key: "tool",
    label: "24h 工具消息",
    value: stats.value.tool_messages_24h.toLocaleString(),
    hint: "工具调用相关消息",
    icon: Connection,
    tagText: runtimeConfig.value.enable_tools ? "功能启用" : "功能关闭",
    tagType: runtimeConfig.value.enable_tools ? "success" : "warning",
  },
  {
    key: "stability",
    label: "模型稳定度",
    value: `${successRate.value}%`,
    hint: "以消息总量估算",
    icon: WarningFilled,
    tagText: healthTagText.value,
    tagType: healthTagType.value,
  },
])

const lastUpdatedText = computed(() => {
  if (!lastUpdatedAt.value) return "-"
  return lastUpdatedAt.value.toLocaleString("zh-CN", { hour12: false })
})

const formatList = (value: unknown) => (Array.isArray(value) ? value.join("、") : "-")

const changeTypeTag = (changeType: string) => {
  const normalized = String(changeType || "").toLowerCase()
  if (normalized === "create") return "success"
  if (normalized === "update") return "warning"
  if (normalized === "delete") return "danger"
  return "info"
}

const loadData = async () => {
  loading.value = true
  try {
    overview.value = await adminApi.getOverview()
    lastUpdatedAt.value = new Date()
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.overview-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.overview-header {
  margin-bottom: 0;
}

.overview-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.overview-updated {
  margin-left: 8px;
  color: #475569;
  font-weight: 500;
}

.overview-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.overview-kpi-card {
  border-radius: 12px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: linear-gradient(155deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
  transition: transform 140ms ease, box-shadow 140ms ease;
}

.overview-kpi-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.09);
}

.overview-kpi-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.overview-kpi-label {
  color: #64748b;
  font-size: 12px;
}

.overview-kpi-icon {
  color: var(--theme-primary-strong);
  font-size: 16px;
}

.overview-kpi-value {
  margin-top: 10px;
  color: #0f172a;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.1;
}

.overview-kpi-foot {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
}

.overview-main-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.overview-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-weight: 600;
  color: #0f172a;
}

.overview-config-grid {
  display: grid;
  gap: 8px;
}

.overview-config-item {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 10px;
  background: #f8fafc;
  padding: 10px 12px;
}

.overview-config-item span {
  display: block;
  color: #64748b;
  font-size: 12px;
  margin-bottom: 4px;
}

.overview-config-item code {
  display: block;
  color: #0f172a;
  font-family: Consolas, "SFMono-Regular", monospace;
  font-size: 12px;
  white-space: normal;
  word-break: break-word;
}

.overview-config-inline {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.inline-metric {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 10px;
  background: #f8fafc;
  padding: 10px 12px;
}

.inline-metric span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.inline-metric strong {
  display: block;
  margin-top: 4px;
  color: #0f172a;
  font-size: 16px;
}

.overview-switches {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.overview-change-card {
  margin-top: 2px;
}

@media (max-width: 1320px) {
  .overview-kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-main-grid {
    grid-template-columns: 1fr;
  }
}
</style>
