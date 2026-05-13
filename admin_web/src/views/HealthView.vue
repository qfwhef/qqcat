<template>
  <div class="health-page">
    <div class="page-header health-header">
      <div>
        <div class="page-title">系统检测</div>
        <div class="page-subtitle">
          检查机器人连接、数据库、模型和工具运行状态
          <span class="health-updated">最后检测：{{ checkedAtText }}</span>
        </div>
      </div>
      <div class="health-actions">
        <el-button :loading="loading" @click="loadData">刷新</el-button>
        <el-button type="primary" :loading="checking" @click="runCheck">一键检测</el-button>
      </div>
    </div>

    <div class="health-summary">
      <div class="summary-item">
        <span>整体状态</span>
        <strong :class="{ danger: overallStatus === 'error' }">{{ overallText }}</strong>
      </div>
      <div class="summary-item">
        <span>Bot 连接数</span>
        <strong>{{ metrics.bot_connections ?? 0 }}</strong>
      </div>
      <div class="summary-item">
        <span>10 分钟 AI 失败</span>
        <strong :class="{ danger: Number(metrics.ai_failures_10m || 0) > 0 }">
          {{ metrics.ai_failures_10m ?? 0 }}
        </strong>
      </div>
      <div class="summary-item">
        <span>工具调用</span>
        <strong>{{ runtime.enable_tools ? "开启" : "关闭" }}</strong>
      </div>
    </div>

    <div class="check-grid">
      <el-card v-for="item in checks" :key="item.key" class="check-card">
        <div class="check-head">
          <div>
            <div class="check-label">{{ item.label }}</div>
            <div class="check-message">{{ item.message || "-" }}</div>
          </div>
          <el-tag :type="tagType(item.status)" effect="light">{{ statusText(item.status) }}</el-tag>
        </div>
        <div class="check-meta">
          <span v-if="item.latency_ms !== undefined">耗时 {{ item.latency_ms }} ms</span>
          <span v-if="item.detail?.tools_supported !== undefined">
            工具参数：{{ item.detail.tools_supported ? "可用" : "不可用" }}
          </span>
        </div>
      </el-card>
    </div>

    <el-card class="page-card detail-card">
      <template #header>
        <div class="panel-title">运行快照</div>
      </template>
      <div class="runtime-grid">
        <div>
          <span>AI Base URL</span>
          <code>{{ runtime.ai_base_url || "-" }}</code>
        </div>
        <div>
          <span>文本模型</span>
          <code>{{ runtime.text_model || "-" }}</code>
        </div>
        <div>
          <span>视觉模型</span>
          <code>{{ runtime.vision_model || "-" }}</code>
        </div>
        <div>
          <span>生图模型</span>
          <code>{{ runtime.image_model || "-" }}</code>
        </div>
        <div>
          <span>摘要记忆</span>
          <code>{{ runtime.enable_summary_memory ? "开启" : "关闭" }}</code>
        </div>
      </div>
      <el-divider content-position="left">最近成功 AI 调用</el-divider>
      <div class="last-call" v-if="metrics.last_success_ai_call">
        <span>{{ metrics.last_success_ai_call.created_at || "-" }}</span>
        <span>{{ metrics.last_success_ai_call.stage || "-" }}</span>
        <span>{{ metrics.last_success_ai_call.model_name || "-" }}</span>
        <span>{{ metrics.last_success_ai_call.latency_ms ?? "-" }} ms</span>
      </div>
      <el-empty v-else description="暂无成功 AI 调用记录" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminApi } from '../api/admin'

const loading = ref(false)
const checking = ref(false)
const health = ref<any | null>(null)

const checks = computed(() => health.value?.checks || [])
const runtime = computed(() => health.value?.runtime || {})
const metrics = computed(() => health.value?.metrics || {})
const overallStatus = computed(() => health.value?.overall_status || 'unknown')
const overallText = computed(() => (overallStatus.value === 'error' ? '需要处理' : '运行正常'))
const checkedAtText = computed(() => {
  const raw = health.value?.checked_at
  if (!raw) return '-'
  return new Date(raw).toLocaleString('zh-CN', { hour12: false })
})

const tagType = (status: string) => {
  if (status === 'normal') return 'success'
  if (status === 'warning') return 'warning'
  if (status === 'error') return 'danger'
  return 'info'
}

const statusText = (status: string) => {
  if (status === 'normal') return '正常'
  if (status === 'warning') return '注意'
  if (status === 'error') return '异常'
  return '未检测'
}

const loadData = async () => {
  loading.value = true
  try {
    health.value = await adminApi.getHealth()
  } finally {
    loading.value = false
  }
}

const runCheck = async () => {
  checking.value = true
  try {
    health.value = await adminApi.checkHealth()
    if (health.value?.overall_status === 'error') {
      ElMessage.warning('检测完成，有项目需要处理')
    } else {
      ElMessage.success('检测完成，系统状态正常')
    }
  } finally {
    checking.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.health-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.health-header {
  margin-bottom: 0;
}

.health-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.health-updated {
  margin-left: 8px;
  color: #475569;
  font-weight: 500;
}

.health-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.summary-item {
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  background: linear-gradient(160deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
}

.summary-item span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.summary-item strong {
  display: block;
  margin-top: 6px;
  color: #0f172a;
  font-size: 22px;
  line-height: 1;
}

.summary-item strong.danger {
  color: #be123c;
}

.check-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.check-card {
  border-radius: 12px;
}

.check-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.check-label {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}

.check-message {
  margin-top: 6px;
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
}

.check-meta {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
}

.detail-card {
  border-radius: 12px;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.runtime-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.runtime-grid div {
  padding: 10px 12px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.runtime-grid span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.runtime-grid code {
  display: block;
  margin-top: 6px;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.last-call {
  display: grid;
  grid-template-columns: 180px 120px 1fr 100px;
  gap: 10px;
  color: #334155;
  font-size: 13px;
}

@media (max-width: 1200px) {
  .health-summary,
  .check-grid,
  .runtime-grid {
    grid-template-columns: 1fr;
  }

  .last-call {
    grid-template-columns: 1fr;
  }
}
</style>
