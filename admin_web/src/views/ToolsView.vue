<template>
  <div class="tools-page">
    <div class="page-header tools-header">
      <div>
        <div class="page-title">工具管理</div>
        <div class="page-subtitle">
          管理内置工具、HTTP 工具与 Python 工具配置，统一控制可用状态
        </div>
      </div>
      <div class="tools-actions">
        <el-button :loading="loading" :icon="Refresh" @click="loadData">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">新增工具</el-button>
      </div>
    </div>

    <el-card class="page-card tools-list-card">
      <template #header>
        <div class="list-head">
          <div class="list-head-title">
            <i />
            <span>工具列表</span>
          </div>
          <div class="list-head-right">
            <span>共 {{ filteredTools.length }} 项</span>
            <el-select v-model="statusFilter" size="small" style="width: 120px">
              <el-option label="全部状态" value="all" />
              <el-option label="仅启用" value="enabled" />
              <el-option label="仅停用" value="disabled" />
            </el-select>
          </div>
        </div>
      </template>

      <el-empty
        v-if="!filteredTools.length"
        description="暂无工具配置"
        :image-size="84"
      >
        <el-button type="primary" @click="openCreateDialog">创建第一个工具</el-button>
      </el-empty>

      <transition-group v-else name="tool-list" tag="div" class="tool-list">
        <div class="tool-list-columns" key="columns">
          <span class="column-main">工具信息</span>
          <span>请求地址/入口</span>
          <span>最近更新</span>
          <span>超时秒数</span>
          <span>状态</span>
          <span>开关</span>
          <span class="column-actions">操作</span>
        </div>
        <article
          v-for="tool in filteredTools"
          :key="tool.tool_name"
          class="tool-item"
          :class="{ disabled: !Boolean(tool.is_enabled) }"
        >
          <div class="tool-grid">
            <div class="tool-main">
              <div class="tool-heading">
                <div class="tool-title-wrap">
                  <div class="tool-avatar">
                    <el-icon><component :is="toolAvatarIcon(tool)" /></el-icon>
                  </div>
                  <div class="tool-title-text">
                    <div class="tool-name-row">
                      <h3>{{ tool.display_name || tool.tool_name }}</h3>
                      <el-tag size="small" type="info">
                        {{
                          tool.tool_type === "http"
                            ? "HTTP"
                            : tool.tool_type === "python"
                              ? "Python"
                              : "内置"
                        }}
                      </el-tag>
                    </div>
                    <code>{{ tool.tool_name }}</code>
                    <p class="tool-desc">{{ tool.description || "暂无描述" }}</p>
                  </div>
                </div>
              </div>
            </div>
            <div class="grid-col mono">{{ tool.tool_type === "python" ? (tool.python_entry || "main") : (tool.url || "-") }}</div>
            <div class="grid-col">{{ tool.updated_at || "-" }}</div>
            <div class="grid-col">{{ tool.tool_type === "python" ? (tool.python_timeout_seconds || "-") : (tool.timeout_seconds || "-") }}</div>
            <div class="grid-col">
              <div class="status-cell" :class="{ active: Boolean(tool.is_enabled) }">
                <i />
                <span>{{ Boolean(tool.is_enabled) ? "已启用" : "已停用" }}</span>
              </div>
            </div>
            <div class="grid-col">
              <el-switch :model-value="Boolean(tool.is_enabled)" @change="toggleTool(tool, $event)" />
            </div>
            <div class="grid-col actions-col">
              <el-button size="small" :icon="EditPen" @click="openEditDialog(tool)">编辑</el-button>
              <el-dropdown trigger="click" @command="onMoreCommand(tool, $event)">
                <el-button size="small" :icon="MoreFilled" />
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit">编辑</el-dropdown-item>
                    <el-dropdown-item v-if="tool.tool_type !== 'builtin'" command="delete">
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </article>
      </transition-group>
    </el-card>

    <el-dialog v-model="dialogVisible" width="820px" class="tool-editor-dialog">
      <template #header>
        <div class="editor-header">
          <div class="editor-heading">
            <h3>{{ dialogTitle }}</h3>
            <p>定义工具能力、输入参数和执行方式</p>
          </div>
          <el-tag effect="dark" round>{{ form.tool_type === 'python' ? 'Python 工具' : 'HTTP 工具' }}</el-tag>
        </div>
      </template>
      <el-form label-position="top" :model="form" class="tool-form-modern">
        <div class="editor-meta-row">
          <el-form-item label="工具类型" class="meta-item">
            <el-segmented
              v-model="form.tool_type"
              :disabled="dialogMode === 'edit'"
              :options="[
                { label: 'HTTP', value: 'http' },
                { label: 'Python', value: 'python' },
              ]"
            />
          </el-form-item>
          <el-form-item label="当前状态" class="meta-item status-item">
            <el-switch v-model="form.is_enabled" />
            <span>{{ form.is_enabled ? '启用' : '停用' }}</span>
          </el-form-item>
        </div>

        <div class="editor-grid">
          <section class="editor-panel">
            <div class="panel-title">基础信息</div>
            <el-form-item label="工具标识">
              <el-input v-model="form.tool_name" :disabled="dialogMode === 'edit'" placeholder="例如 get_joke" />
            </el-form-item>
            <el-form-item label="显示名称">
              <el-input v-model="form.display_name" placeholder="例如 随机笑话" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="form.description" type="textarea" :rows="3" />
            </el-form-item>
          </section>

          <section class="editor-panel">
            <transition name="type-panel" mode="out-in">
              <div v-if="form.tool_type === 'http'" key="http">
                <div class="panel-title">HTTP 执行配置</div>
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
              <div v-else key="python">
                <div class="panel-title">Python 执行配置</div>
                <el-form-item label="入口函数">
                  <el-input v-model="form.python_entry" placeholder="默认 main" />
                </el-form-item>
                <el-form-item label="执行超时秒数">
                  <el-input-number v-model="form.python_timeout_seconds" :min="1" :max="60" />
                </el-form-item>
                <el-form-item label="允许导入模块">
                  <el-switch v-model="form.python_allow_network" />
                </el-form-item>
              </div>
            </transition>
          </section>
        </div>

        <section class="editor-panel full">
          <div class="panel-title">参数定义</div>
          <el-form-item label="参数 Schema(JSON)">
            <div class="field-actions">
              <el-button text size="small" @click="fillDefaultSchema">填充默认 Schema</el-button>
            </div>
            <el-input v-model="parametersRaw" type="textarea" :rows="8" placeholder='{"type":"object","properties":{...}}' />
          </el-form-item>
        </section>

        <section v-if="form.tool_type === 'http'" class="editor-panel full">
          <div class="panel-title">HTTP 细节</div>
          <el-form-item label="Headers(JSON)">
            <el-input v-model="headersRaw" type="textarea" :rows="5" placeholder='{"Authorization":"Bearer {{token}}"}' />
          </el-form-item>
          <el-form-item label="Body 模板">
            <el-input
              v-model="form.body_template"
              type="textarea"
              :rows="6"
              placeholder='留空时默认将工具参数整体作为 JSON Body；也支持 {"query":"{{query}}"} 模板'
            />
          </el-form-item>
        </section>

        <section v-if="form.tool_type === 'python'" class="editor-panel full">
          <div class="panel-title">Python 代码</div>
          <div class="field-actions">
            <el-button text size="small" @click="fillPythonTemplate('echo')">模板：参数回显</el-button>
            <el-button text size="small" @click="fillPythonTemplate('calc')">模板：简单计算</el-button>
          </div>
          <el-input
            class="python-editor"
            v-model="form.python_code"
            type="textarea"
            :rows="12"
            placeholder='def main(args):\n    return {"ok": True, "echo": args}'
          />
        </section>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTool">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Connection,
  Cpu,
  EditPen,
  MoreFilled,
  Opportunity,
  Plus,
  Refresh,
  Timer,
} from '@element-plus/icons-vue'

import { adminApi } from '../api/admin'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const tools = ref<any[]>([])
const statusFilter = ref<'all' | 'enabled' | 'disabled'>('all')
const parametersRaw = ref('')
const headersRaw = ref('')
const form = reactive({
  tool_type: 'http',
  tool_name: '',
  display_name: '',
  description: '',
  method: 'GET',
  url: '',
  timeout_seconds: 15,
  python_code: '',
  python_entry: 'main',
  python_allow_network: false,
  python_timeout_seconds: 8,
  is_enabled: true,
  body_template: '',
})

const filteredTools = computed(() => {
  if (statusFilter.value === 'enabled') return tools.value.filter((item) => Boolean(item.is_enabled))
  if (statusFilter.value === 'disabled') return tools.value.filter((item) => !Boolean(item.is_enabled))
  return tools.value
})
const dialogTitle = computed(() => {
  if (dialogMode.value === 'edit') return '编辑工具'
  return form.tool_type === 'python' ? '新增 Python 工具' : '新增 HTTP 工具'
})

const toolAvatarIcon = (tool: any) => {
  if (tool.tool_type === 'http') return Connection
  if (String(tool.tool_name || '').includes('time')) return Timer
  if (String(tool.tool_name || '').includes('weather')) return Opportunity
  return Cpu
}

const resetForm = () => {
  form.tool_type = 'http'
  form.tool_name = ''
  form.display_name = ''
  form.description = ''
  form.method = 'GET'
  form.url = ''
  form.timeout_seconds = 15
  form.python_code = ''
  form.python_entry = 'main'
  form.python_allow_network = false
  form.python_timeout_seconds = 8
  form.is_enabled = true
  form.body_template = ''
  fillDefaultSchema()
  headersRaw.value = '{}'
}

const fillDefaultSchema = () => {
  parametersRaw.value = JSON.stringify(
    { type: 'object', properties: {}, additionalProperties: true },
    null,
    2,
  )
}

const fillPythonTemplate = (kind: 'echo' | 'calc') => {
  if (kind === 'calc') {
    form.python_code = [
      'def main(args):',
      '    a = float(args.get("a", 0))',
      '    b = float(args.get("b", 0))',
      '    op = str(args.get("op", "+"))',
      '    if op == "+":',
      '        value = a + b',
      '    elif op == "-":',
      '        value = a - b',
      '    elif op == "*":',
      '        value = a * b',
      '    elif op == "/":',
      '        value = a / b if b else None',
      '    else:',
      '        value = None',
      '    return {"a": a, "b": b, "op": op, "result": value}',
    ].join('\n')
    return
  }
  form.python_code = [
    'def main(args):',
    '    text = str(args.get("text", ""))',
    '    return {',
    '        "text": text,',
    '        "length": len(text),',
    '        "args": args,',
    '    }',
  ].join('\n')
}

watch(
  () => form.tool_type,
  (nextType) => {
    if (dialogMode.value !== 'create') return
    if (nextType === 'python') {
      form.python_entry = form.python_entry.trim() || 'main'
      form.python_timeout_seconds = form.python_timeout_seconds || 8
      if (!form.python_code.trim()) fillPythonTemplate('echo')
      return
    }
    form.method = form.method || 'GET'
    form.timeout_seconds = form.timeout_seconds || 15
  },
)

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
  form.tool_type = row.tool_type === 'python' ? 'python' : 'http'
  form.tool_name = row.tool_name
  form.display_name = row.display_name || ''
  form.description = row.description || ''
  form.method = row.method || 'GET'
  form.url = row.url || ''
  form.timeout_seconds = Number(row.timeout_seconds || 15)
  form.python_code = row.python_code || ''
  form.python_entry = row.python_entry || 'main'
  form.python_allow_network = Boolean(row.python_allow_network)
  form.python_timeout_seconds = Number(row.python_timeout_seconds || 8)
  form.is_enabled = Boolean(row.is_enabled)
  form.body_template = row.body_template || ''
  parametersRaw.value = JSON.stringify(
    row.parameters_json || { type: 'object', properties: {}, additionalProperties: true },
    null,
    2,
  )
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
  if (form.tool_type === 'http' && dialogMode.value === 'create' && !form.url.trim()) {
    ElMessage.warning('请填写 URL')
    return
  }
  if (form.tool_type === 'python' && !form.python_code.trim()) {
    ElMessage.warning('请填写 Python 代码')
    return
  }
  saving.value = true
  try {
    const commonPayload = {
      tool_name: form.tool_name.trim(),
      display_name: form.display_name.trim() || form.tool_name.trim(),
      description: form.description.trim(),
      is_enabled: form.is_enabled,
      parameters_json: parseJsonField(parametersRaw.value, '参数 Schema'),
    }
    if (dialogMode.value === 'create') {
      if (form.tool_type === 'python') {
        const payload = {
          ...commonPayload,
          python_code: form.python_code,
          python_entry: form.python_entry.trim() || 'main',
          python_allow_network: form.python_allow_network,
          python_timeout_seconds: form.python_timeout_seconds,
        }
        await adminApi.createPythonTool(payload)
        ElMessage.success('Python 工具已创建')
      } else {
        const payload = {
          ...commonPayload,
          method: form.method,
          url: form.url.trim(),
          timeout_seconds: form.timeout_seconds,
          body_template: form.body_template.trim() || undefined,
          headers_json: parseJsonField(headersRaw.value, 'Headers'),
        }
        await adminApi.createHttpTool(payload)
        ElMessage.success('HTTP 工具已创建')
      }
    } else {
      const payload = form.tool_type === 'python'
        ? {
            ...commonPayload,
            python_code: form.python_code,
            python_entry: form.python_entry.trim() || 'main',
            python_allow_network: form.python_allow_network,
            python_timeout_seconds: form.python_timeout_seconds,
          }
        : {
            ...commonPayload,
            method: form.method,
            url: form.url.trim(),
            timeout_seconds: form.timeout_seconds,
            body_template: form.body_template.trim() || undefined,
            headers_json: parseJsonField(headersRaw.value, 'Headers'),
          }
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
  try {
    await adminApi.updateTool(row.tool_name, { is_enabled: enabled })
    row.is_enabled = enabled
    ElMessage.success(enabled ? '工具已启用' : '工具已停用')
  } catch {
    ElMessage.error('状态更新失败')
  }
}

const onMoreCommand = async (row: any, command: string) => {
  if (command === 'edit') {
    openEditDialog(row)
    return
  }
  if (command === 'delete' && row.tool_type !== 'builtin') {
    await handleDelete(row)
  }
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除工具 ${row.tool_name} 吗？`, '删除工具', { type: 'warning' })
  await adminApi.deleteTool(row.tool_name)
  ElMessage.success('工具已删除')
  await loadData()
}

onMounted(loadData)
</script>

<style scoped>
.tools-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  animation: pageFadeIn 300ms ease;
}

.tools-header {
  margin-bottom: 0;
}

.tools-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tools-list-card {
  border-radius: 12px;
}

.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.list-head-title {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
}

.list-head-title i {
  width: 4px;
  height: 18px;
  border-radius: 999px;
  background: var(--theme-primary);
}

.list-head-right {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: #475569;
  font-size: 13px;
}

.tool-list {
  display: grid;
  gap: 10px;
}

.tool-list-columns {
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: #f8fafc;
  padding: 10px 14px;
  display: grid;
  grid-template-columns: minmax(260px, 2.3fr) minmax(140px, 1fr) minmax(140px, 1fr) minmax(96px, 0.7fr) minmax(84px, 0.6fr) minmax(90px, 0.6fr) minmax(120px, 0.8fr);
  gap: 10px;
  align-items: center;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.tool-list-columns .column-main {
  padding-left: 8px;
}

.tool-list-columns .column-actions {
  text-align: right;
}

.tool-item {
  border-radius: 14px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: #ffffff;
  padding: 12px 14px;
  transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
}

.tool-item:hover {
  transform: translateY(-2px);
  border-color: rgba(var(--theme-primary-rgb), 0.28);
  box-shadow: 0 10px 20px rgba(15, 23, 42, 0.07);
}

.tool-item.disabled {
  opacity: 0.7;
}

.tool-grid {
  display: grid;
  grid-template-columns: minmax(260px, 2.3fr) minmax(140px, 1fr) minmax(140px, 1fr) minmax(96px, 0.7fr) minmax(84px, 0.6fr) minmax(90px, 0.6fr) minmax(120px, 0.8fr);
  gap: 10px;
  align-items: center;
}

.tool-heading {
  display: flex;
  align-items: center;
}

.tool-main {
  min-width: 0;
}

.tool-title-wrap h3 {
  margin: 0;
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
}

.tool-title-wrap {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.tool-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 18px;
  color: var(--theme-primary);
  background: rgba(var(--theme-primary-rgb), 0.14);
}

.tool-title-text {
  min-width: 0;
}

.tool-name-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tool-title-wrap code {
  display: inline-block;
  margin-top: 4px;
  color: #475569;
  font-family: Consolas, "SFMono-Regular", monospace;
  font-size: 13px;
  line-height: 1;
}

.tool-desc {
  margin: 6px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.grid-col {
  color: #1e293b;
  font-size: 14px;
  font-weight: 500;
}

.grid-col.mono {
  font-family: Consolas, "SFMono-Regular", monospace;
  font-size: 14px;
  color: #475569;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 14px;
  font-weight: 600;
}

.status-cell i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
}

.status-cell.active {
  color: #16a34a;
}

.status-cell.active i {
  background: #22c55e;
}

.actions-col {
  display: inline-flex;
  justify-content: flex-end;
  gap: 8px;
}

.actions-col :deep(.el-button + .el-dropdown) {
  margin-left: 0;
}

.tool-form-modern {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

:deep(.tool-editor-dialog .el-dialog) {
  border-radius: 14px;
  overflow: hidden;
}

:deep(.tool-editor-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 18px 20px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  background: linear-gradient(135deg, #f8fbff, #f3f7fd);
}

:deep(.tool-editor-dialog .el-dialog__body) {
  padding: 14px 20px 12px;
}

:deep(.tool-editor-dialog .el-dialog__footer) {
  padding: 12px 20px 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
  background: #fbfdff;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.editor-heading h3 {
  margin: 0;
  color: #0f172a;
  font-size: 17px;
  line-height: 1.2;
}

.editor-heading p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
}

.editor-meta-row {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 10px;
}

.meta-item {
  margin-bottom: 0;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: #f8fafd;
}

.status-item :deep(.el-form-item__content) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #334155;
  font-size: 13px;
}

.editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.editor-panel {
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: #ffffff;
  padding: 12px;
}

.editor-panel.full {
  margin-top: -2px;
}

.panel-title {
  margin-bottom: 10px;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}

.editor-panel :deep(.el-form-item) {
  margin-bottom: 10px;
}

.editor-panel :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

.field-actions {
  margin-bottom: 6px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.python-editor :deep(.el-textarea__inner) {
  font-family: Consolas, "SFMono-Regular", monospace;
  font-size: 13px;
  line-height: 1.45;
  min-height: 250px;
  border-radius: 10px;
  background: #0f172a;
  color: #e2e8f0;
}

.python-editor :deep(.el-textarea__inner::placeholder) {
  color: #94a3b8;
}

.type-panel-enter-active,
.type-panel-leave-active {
  transition: all 220ms ease;
}

.type-panel-enter-from,
.type-panel-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.tool-list-enter-active,
.tool-list-leave-active {
  transition: all 260ms ease;
}

.tool-list-enter-from,
.tool-list-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@keyframes pageFadeIn {
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
  .tool-list-columns {
    display: none;
  }

  .tool-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .grid-col,
  .grid-col.mono {
    font-size: 14px;
    font-weight: 500;
  }

  .actions-col {
    justify-content: flex-start;
  }

  .editor-meta-row,
  .editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
