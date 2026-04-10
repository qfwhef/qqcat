<template>
  <div>
    <div class="page-header">
      <div class="page-title">系统概览</div>
      <el-button :loading="loading" @click="loadData">刷新概览</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">24h 消息数</div>
        <div class="stat-value">{{ overview?.stats?.messages_24h ?? 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">24h 摘要数</div>
        <div class="stat-value">{{ overview?.stats?.summaries_24h ?? 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">24h 工具消息</div>
        <div class="stat-value">{{ overview?.stats?.tool_messages_24h ?? 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">24h AI 失败</div>
        <div class="stat-value">{{ overview?.stats?.ai_failures_24h ?? 0 }}</div>
      </div>
    </div>

    <div class="split-grid">
      <el-card class="page-card">
        <template #header>当前运行配置</template>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="AI Base URL">{{ overview?.runtime_config?.ai_base_url || '-' }}</el-descriptions-item>
          <el-descriptions-item label="文本模型">{{ overview?.runtime_config?.text_model || '-' }}</el-descriptions-item>
          <el-descriptions-item label="视觉模型">{{ overview?.runtime_config?.vision_model || '-' }}</el-descriptions-item>
          <el-descriptions-item label="文本回滚链">{{ formatList(overview?.runtime_config?.text_model_fallback) }}</el-descriptions-item>
          <el-descriptions-item label="视觉回滚链">{{ formatList(overview?.runtime_config?.vision_model_fallback) }}</el-descriptions-item>
          <el-descriptions-item label="默认回复率">{{ overview?.runtime_config?.default_reply_rate ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="最大历史条数">{{ overview?.runtime_config?.max_history ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="日志级别">{{ overview?.runtime_config?.log_level || '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="page-card">
        <template #header>最近失败 AI 调用</template>
        <el-table :data="overview?.recent_failures || []" height="420">
          <el-table-column prop="created_at" label="时间" min-width="160" />
          <el-table-column prop="session_type" label="会话类型" width="100" />
          <el-table-column prop="session_id" label="会话ID" min-width="120" />
          <el-table-column prop="stage" label="阶段" min-width="120" />
          <el-table-column prop="model_name" label="模型" min-width="180" />
          <el-table-column prop="failure_reason" label="失败原因" min-width="120" />
        </el-table>
      </el-card>
    </div>

    <el-card class="page-card" style="margin-top: 20px">
      <template #header>最近配置变更</template>
      <el-table :data="overview?.recent_config_changes || []">
        <el-table-column prop="created_at" label="时间" min-width="160" />
        <el-table-column prop="config_domain" label="配置域" min-width="140" />
        <el-table-column prop="scope_ref" label="作用域" min-width="160" />
        <el-table-column prop="change_type" label="操作" width="100" />
        <el-table-column prop="changed_by" label="操作人" min-width="140" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { adminApi } from '../api/admin'

const loading = ref(false)
const overview = ref<any>(null)

const formatList = (value: unknown) => (Array.isArray(value) ? value.join('\n') : '-')

const loadData = async () => {
  loading.value = true
  try {
    overview.value = await adminApi.getOverview()
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>
