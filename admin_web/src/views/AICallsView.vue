<template>
  <div>
    <el-card class="page-card">
      <div ref="logsContentRef" class="logs-content">
        <el-form ref="filterFormRef" :inline="true" class="toolbar-form compact-filter-form">
          <el-form-item label="会话类型">
            <el-select v-model="filters.session_type" clearable style="width: 120px">
              <el-option label="group" value="group" />
              <el-option label="private" value="private" />
            </el-select>
          </el-form-item>
          <el-form-item label="会话 ID">
            <el-input v-model.number="filters.session_id" placeholder="群号/用户QQ" style="width: 160px" clearable />
          </el-form-item>
          <el-form-item label="阶段">
            <el-input v-model="filters.stage" placeholder="chat/summary" style="width: 160px" clearable />
          </el-form-item>
          <el-form-item label="模型">
            <el-input v-model="filters.model_name" placeholder="模型名模糊匹配" style="width: 180px" clearable />
          </el-form-item>
          <el-form-item label="失败原因">
            <el-input v-model="filters.failure_reason" placeholder="rate_limit 等" style="width: 180px" clearable />
          </el-form-item>
          <el-form-item label="成功状态">
            <el-select v-model="filters.is_success" clearable style="width: 120px">
              <el-option label="成功" :value="true" />
              <el-option label="失败" :value="false" />
            </el-select>
          </el-form-item>
          <el-form-item label="开始时间">
            <el-input v-model="filters.start_at" placeholder="YYYY-MM-DD HH:mm:ss" style="width: 180px" clearable />
          </el-form-item>
          <el-form-item label="结束时间">
            <el-input v-model="filters.end_at" placeholder="YYYY-MM-DD HH:mm:ss" style="width: 180px" clearable />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" @click="handleSearch">查询</el-button>
          </el-form-item>
        </el-form>

        <div class="table-scroll-shell">
          <el-table :data="rows.items" :max-height="tableMaxHeight">
            <el-table-column prop="id" label="ID" width="90" />
            <el-table-column prop="created_at" label="时间" min-width="160" />
            <el-table-column prop="session_type" label="会话类型" width="100" />
            <el-table-column prop="session_id" label="会话ID" min-width="120" />
            <el-table-column prop="stage" label="阶段" min-width="140" />
            <el-table-column prop="model_name" label="模型" min-width="200" />
            <el-table-column prop="fallback_index" label="回滚层级" width="100" />
            <el-table-column label="tools" width="90">
              <template #default="{ row }">{{ row.allow_tools ? '开' : '关' }}</template>
            </el-table-column>
            <el-table-column label="结果" width="90">
              <template #default="{ row }">
                <el-tag :type="row.is_success ? 'success' : 'danger'">{{ row.is_success ? '成功' : '失败' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="failure_reason" label="失败原因" min-width="130" />
            <el-table-column prop="latency_ms" label="耗时(ms)" width="100" />
            <el-table-column prop="request_excerpt" label="请求摘要" min-width="260" show-overflow-tooltip />
          </el-table>
        </div>
        <div ref="paginationBarRef" class="logs-pagination-bar">
          <el-pagination
            background
            layout="total, prev, pager, next"
            :total="rows.total"
            :page-size="rows.page_size"
            :current-page="rows.page"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { adminApi } from '../api/admin'

const loading = ref(false)
const logsContentRef = ref<HTMLElement | null>(null)
const filterFormRef = ref<any>(null)
const paginationBarRef = ref<HTMLElement | null>(null)
const tableMaxHeightPx = ref(320)
let resizeObserver: ResizeObserver | null = null
const rows = reactive({ items: [] as any[], page: 1, page_size: 20, total: 0 })
const filters = reactive({
  session_type: '',
  session_id: undefined as number | undefined,
  stage: '',
  model_name: '',
  failure_reason: '',
  is_success: undefined as boolean | undefined,
  start_at: '',
  end_at: '',
})

const tableMaxHeight = computed(() => Math.max(220, tableMaxHeightPx.value))

const getElementHeight = (target: any) => {
  const el = target?.$el ?? target
  return el instanceof HTMLElement ? el.offsetHeight : 0
}

const recalcTableHeight = async () => {
  await nextTick()
  const container = logsContentRef.value
  if (!container) return
  const top = container.getBoundingClientRect().top
  const viewport = window.innerHeight
  const formHeight = getElementHeight(filterFormRef.value)
  const paginationHeight = getElementHeight(paginationBarRef.value)
  const available = viewport - top - 24
  tableMaxHeightPx.value = available - formHeight - paginationHeight - 18
}

const loadData = async () => {
  loading.value = true
  try {
    const data = await adminApi.getAiCallLogs({
      page: rows.page,
      page_size: rows.page_size,
      ...filters,
    })
    Object.assign(rows, data)
  } finally {
    loading.value = false
  }
}

const handleSearch = async () => {
  rows.page = 1
  await loadData()
  await recalcTableHeight()
}

const handlePageChange = async (page: number) => {
  rows.page = page
  await loadData()
}

onMounted(async () => {
  resizeObserver = new ResizeObserver(() => {
    void recalcTableHeight()
  })
  window.addEventListener('resize', recalcTableHeight)
  await loadData()
  await recalcTableHeight()
  if (logsContentRef.value) resizeObserver.observe(logsContentRef.value)
  const filterEl = filterFormRef.value?.$el
  if (filterEl instanceof HTMLElement) resizeObserver.observe(filterEl)
  if (paginationBarRef.value) resizeObserver.observe(paginationBarRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', recalcTableHeight)
})
</script>

<style scoped>
.logs-content {
  display: flex;
  flex-direction: column;
}

.compact-filter-form {
  margin: 8px 0;
}

.table-scroll-shell {
  overflow: hidden;
  margin-top: 8px;
}

.logs-pagination-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-height: 32px;
  margin-top: 6px;
  background: #fff;
}

:deep(.page-card > .el-card__body) {
  padding-bottom: 2px !important;
}
</style>
