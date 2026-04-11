<template>
  <div>
    <div class="page-header">
      <div class="page-title">定时任务</div>
      <div style="display: flex; gap: 10px">
        <el-button :loading="loading" @click="loadData">刷新</el-button>
        <el-button type="primary" @click="openCreateDialog">新增任务</el-button>
      </div>
    </div>

    <el-card class="page-card">
      <el-form :inline="true" class="toolbar-form compact-filter-form">
        <el-form-item label="关键词">
          <el-input v-model="filters.keyword" placeholder="名称/描述/消息内容" clearable style="width: 220px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable style="width: 120px">
            <el-option label="active" value="active" />
            <el-option label="paused" value="paused" />
            <el-option label="completed" value="completed" />
          </el-select>
        </el-form-item>
        <el-form-item label="投递类型">
          <el-select v-model="filters.target_type" clearable style="width: 120px">
            <el-option label="group" value="group" />
            <el-option label="private" value="private" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSearch">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows.items">
        <el-table-column prop="name" label="任务名" min-width="140" />
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="schedule_type" label="类型" width="100" />
        <el-table-column label="投递目标" min-width="180">
          <template #default="{ row }">
            {{ row.target_type }}: {{ (row.target_ids || []).join(', ') }}
          </template>
        </el-table-column>
        <el-table-column prop="last_run_at" label="上次运行" min-width="160" />
        <el-table-column prop="next_run_at" label="下次运行" min-width="160" />
        <el-table-column prop="last_run_status" label="上次结果" width="100" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div style="display: flex; gap: 8px">
              <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
              <el-button link type="success" @click="handleRunNow(row)">立即运行</el-button>
              <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div style="display: flex; justify-content: flex-end; margin-top: 12px">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="rows.total"
          :page-size="rows.page_size"
          :current-page="rows.page"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogMode === 'create' ? '新增定时任务' : '编辑定时任务'" width="760px">
      <el-form :model="form" label-position="top">
        <div class="split-grid">
          <div>
            <el-form-item label="任务名">
              <el-input v-model="form.name" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="form.description" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="active" value="active" />
                <el-option label="paused" value="paused" />
                <el-option label="completed" value="completed" />
              </el-select>
            </el-form-item>
            <el-form-item label="投递类型">
              <el-select v-model="form.target_type" style="width: 100%">
                <el-option label="group" value="group" />
                <el-option label="private" value="private" />
              </el-select>
            </el-form-item>
            <el-form-item label="投递目标">
              <el-input v-model="targetIdsRaw" type="textarea" :rows="3" placeholder="每行一个 QQ/群号，也支持逗号分隔" />
            </el-form-item>
          </div>
          <div>
            <el-form-item label="调度类型">
              <el-select v-model="form.schedule_type" style="width: 100%">
                <el-option label="once" value="once" />
                <el-option label="interval" value="interval" />
                <el-option label="cron" value="cron" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.schedule_type === 'once'" label="运行时间">
              <el-input v-model="form.run_at" placeholder="YYYY-MM-DD HH:mm:ss" />
            </el-form-item>
            <el-form-item v-if="form.schedule_type === 'interval'" label="间隔秒数">
              <el-input-number v-model="form.interval_seconds" :min="1" :max="31536000" />
            </el-form-item>
            <el-form-item v-if="form.schedule_type === 'cron'" label="Cron 表达式">
              <el-input v-model="form.cron_expression" placeholder="例如 */5 * * * *" />
            </el-form-item>
            <el-form-item label="消息内容">
              <el-input v-model="form.message_content" type="textarea" :rows="8" />
            </el-form-item>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTask">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminApi } from '../api/admin'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const editingTaskId = ref<number | null>(null)
const targetIdsRaw = ref('')
const rows = reactive({ items: [] as any[], page: 1, page_size: 20, total: 0 })
const filters = reactive({
  keyword: '',
  status: '',
  target_type: '',
})
const form = reactive({
  name: '',
  description: '',
  status: 'active',
  schedule_type: 'once',
  cron_expression: '',
  run_at: '',
  interval_seconds: 3600,
  target_type: 'group',
  message_content: '',
})

const parseTargetIds = (raw: string) =>
  raw
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item) && item > 0)

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.status = 'active'
  form.schedule_type = 'once'
  form.cron_expression = ''
  form.run_at = ''
  form.interval_seconds = 3600
  form.target_type = 'group'
  form.message_content = ''
  targetIdsRaw.value = ''
}

const loadData = async () => {
  loading.value = true
  try {
    const data = await adminApi.getScheduledTasks({
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
}

const handlePageChange = async (page: number) => {
  rows.page = page
  await loadData()
}

const openCreateDialog = () => {
  dialogMode.value = 'create'
  editingTaskId.value = null
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (row: any) => {
  dialogMode.value = 'edit'
  editingTaskId.value = Number(row.id)
  form.name = row.name || ''
  form.description = row.description || ''
  form.status = row.status || 'active'
  form.schedule_type = row.schedule_type || 'once'
  form.cron_expression = row.cron_expression || ''
  form.run_at = row.run_at || ''
  form.interval_seconds = Number(row.interval_seconds || 3600)
  form.target_type = row.target_type || 'group'
  form.message_content = row.message_content || ''
  targetIdsRaw.value = Array.isArray(row.target_ids) ? row.target_ids.join('\n') : ''
  dialogVisible.value = true
}

const saveTask = async () => {
  const payload = {
    ...form,
    target_ids: parseTargetIds(targetIdsRaw.value),
    cron_expression: form.schedule_type === 'cron' ? form.cron_expression || undefined : undefined,
    run_at: form.schedule_type === 'once' ? form.run_at || undefined : undefined,
    interval_seconds: form.schedule_type === 'interval' ? form.interval_seconds : undefined,
  }
  saving.value = true
  try {
    if (dialogMode.value === 'create') {
      await adminApi.createScheduledTask(payload)
      ElMessage.success('定时任务已创建')
    } else if (editingTaskId.value != null) {
      await adminApi.updateScheduledTask(editingTaskId.value, payload)
      ElMessage.success('定时任务已更新')
    }
    dialogVisible.value = false
    await loadData()
  } finally {
    saving.value = false
  }
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除定时任务 ${row.name} 吗？`, '删除定时任务', { type: 'warning' })
  await adminApi.deleteScheduledTask(Number(row.id))
  ElMessage.success('定时任务已删除')
  await loadData()
}

const handleRunNow = async (row: any) => {
  await adminApi.runScheduledTaskNow(Number(row.id))
  ElMessage.success('定时任务已执行')
  await loadData()
}

onMounted(loadData)
</script>
