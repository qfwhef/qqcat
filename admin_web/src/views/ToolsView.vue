<template>
  <div>
    <el-card class="page-card">
      <div class="table-toolbar" style="margin-bottom: 8px">
        <div style="font-size: 16px; font-weight: 700; color: #111827">工具管理</div>
        <div style="display: flex; gap: 10px">
          <el-button :loading="loading" @click="loadData">刷新</el-button>
          <el-button type="primary" @click="openCreateDialog">新增 HTTP 工具</el-button>
        </div>
      </div>
      <el-table :data="tools">
        <el-table-column prop="display_name" label="工具名" min-width="140">
          <template #default="{ row }">{{ row.display_name || row.tool_name }}</template>
        </el-table-column>
        <el-table-column prop="tool_name" label="标识" min-width="150" />
        <el-table-column prop="tool_type" label="类型" width="90" />
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column prop="method" label="方法" width="90" />
        <el-table-column prop="url" label="URL" min-width="220" show-overflow-tooltip />
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch :model-value="Boolean(row.is_enabled)" @change="toggleTool(row, $event)" />
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" min-width="160" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <div style="display: flex; gap: 8px">
              <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
              <el-button v-if="row.tool_type === 'http'" link type="danger" @click="handleDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogMode === 'create' ? '新增 HTTP 工具' : '编辑工具'" width="760px">
      <el-form label-position="top" :model="form">
        <div class="split-grid">
          <div>
            <el-form-item label="工具标识">
              <el-input v-model="form.tool_name" :disabled="dialogMode === 'edit'" placeholder="例如 get_joke" />
            </el-form-item>
            <el-form-item label="显示名称">
              <el-input v-model="form.display_name" placeholder="例如 随机笑话" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="form.description" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="form.is_enabled" />
            </el-form-item>
          </div>
          <div>
            <el-form-item label="HTTP 方法">
              <el-select v-model="form.method" style="width: 100%">
                <el-option label="GET" value="GET" />
                <el-option label="POST" value="POST" />
                <el-option label="PUT" value="PUT" />
                <el-option label="DELETE" value="DELETE" />
              </el-select>
            </el-form-item>
            <el-form-item label="URL">
              <el-input v-model="form.url" placeholder="支持 {{param}} 占位符" />
            </el-form-item>
            <el-form-item label="超时秒数">
              <el-input-number v-model="form.timeout_seconds" :min="1" :max="300" />
            </el-form-item>
          </div>
        </div>
        <el-form-item label="参数 Schema(JSON)">
          <el-input v-model="parametersRaw" type="textarea" :rows="8" placeholder='{"type":"object","properties":{...}}' />
        </el-form-item>
        <el-form-item label="Headers(JSON)">
          <el-input v-model="headersRaw" type="textarea" :rows="6" placeholder='{"Authorization":"Bearer {{token}}"}' />
        </el-form-item>
        <el-form-item label="Body 模板">
          <el-input
            v-model="form.body_template"
            type="textarea"
            :rows="6"
            placeholder='留空时默认将工具参数整体作为 JSON Body；也支持 {"query":"{{query}}"} 模板'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTool">保存</el-button>
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
const tools = ref<any[]>([])
const parametersRaw = ref('')
const headersRaw = ref('')
const form = reactive({
  tool_name: '',
  display_name: '',
  description: '',
  method: 'GET',
  url: '',
  timeout_seconds: 15,
  is_enabled: true,
  body_template: '',
})

const resetForm = () => {
  form.tool_name = ''
  form.display_name = ''
  form.description = ''
  form.method = 'GET'
  form.url = ''
  form.timeout_seconds = 15
  form.is_enabled = true
  form.body_template = ''
  parametersRaw.value = JSON.stringify(
    { type: 'object', properties: {}, additionalProperties: true },
    null,
    2,
  )
  headersRaw.value = '{}'
}

const loadData = async () => {
  loading.value = true
  try {
    const data = await adminApi.getTools()
    tools.value = data.items || []
  } finally {
    loading.value = false
  }
}

const openCreateDialog = () => {
  dialogMode.value = 'create'
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (row: any) => {
  dialogMode.value = 'edit'
  form.tool_name = row.tool_name
  form.display_name = row.display_name || ''
  form.description = row.description || ''
  form.method = row.method || 'GET'
  form.url = row.url || ''
  form.timeout_seconds = Number(row.timeout_seconds || 15)
  form.is_enabled = Boolean(row.is_enabled)
  form.body_template = row.body_template || ''
  parametersRaw.value = JSON.stringify(row.parameters_json || { type: 'object', properties: {}, additionalProperties: true }, null, 2)
  headersRaw.value = JSON.stringify(row.headers_json || {}, null, 2)
  dialogVisible.value = true
}

const parseJsonField = (raw: string, fieldName: string) => {
  try {
    return raw.trim() ? JSON.parse(raw) : {}
  } catch {
    throw new Error(`${fieldName} 不是合法 JSON`)
  }
}

const saveTool = async () => {
  if (!form.tool_name.trim()) {
    ElMessage.warning('请填写工具标识')
    return
  }
  if (!form.description.trim()) {
    ElMessage.warning('请填写工具描述')
    return
  }
  if (dialogMode.value === 'create' && !form.url.trim()) {
    ElMessage.warning('请填写 URL')
    return
  }
  saving.value = true
  try {
    const payload = {
      tool_name: form.tool_name.trim(),
      display_name: form.display_name.trim() || form.tool_name.trim(),
      description: form.description.trim(),
      method: form.method,
      url: form.url.trim(),
      timeout_seconds: form.timeout_seconds,
      is_enabled: form.is_enabled,
      body_template: form.body_template.trim() || undefined,
      parameters_json: parseJsonField(parametersRaw.value, '参数 Schema'),
      headers_json: parseJsonField(headersRaw.value, 'Headers'),
    }
    if (dialogMode.value === 'create') {
      await adminApi.createHttpTool(payload)
      ElMessage.success('HTTP 工具已创建')
    } else {
      await adminApi.updateTool(form.tool_name, payload)
      ElMessage.success('工具已更新')
    }
    dialogVisible.value = false
    await loadData()
  } catch (error: any) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const toggleTool = async (row: any, value: boolean | string | number) => {
  const enabled = Boolean(value)
  await adminApi.updateTool(row.tool_name, { is_enabled: enabled })
  row.is_enabled = enabled
  ElMessage.success(enabled ? '工具已启用' : '工具已停用')
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除工具 ${row.tool_name} 吗？`, '删除工具', { type: 'warning' })
  await adminApi.deleteTool(row.tool_name)
  ElMessage.success('工具已删除')
  await loadData()
}

onMounted(loadData)
</script>
