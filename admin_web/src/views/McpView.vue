<template>
  <div class="mcp-page">
    <div class="page-header">
      <div>
        <div class="page-title">MCP 服务</div>
        <div class="page-subtitle">连接外部 MCP Server，将 tools 接入猫娘工具调用链路</div>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadData">刷新</el-button>
        <el-button :icon="Download" @click="openDownloadDialog">下载 MCP</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateDialog">新增服务</el-button>
      </div>
    </div>

    <el-card class="page-card">
      <template #header>
        <div class="section-head">
          <span>常用预设</span>
          <el-tag type="warning">默认仅管理员</el-tag>
        </div>
      </template>
      <div class="preset-grid">
        <div
          v-for="preset in mcpPresets"
          :key="preset.server_name"
          class="preset-item"
          @click="openPresetDialog(preset)"
        >
          <strong>{{ preset.display_name }}</strong>
          <span>{{ preset.summary }}</span>
          <code>{{ preset.command }} {{ preset.args_json.join(' ') }}</code>
          <div class="preset-actions">
            <el-button
              size="small"
              :icon="Download"
              :loading="installingName === preset.server_name"
              @click.stop="installPreset(preset)"
            >
              {{ presetInstalled(preset) ? '重新安装' : '一键安装' }}
            </el-button>
            <el-tag v-if="presetInstalled(preset)" size="small" type="success">已配置</el-tag>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="page-card">
      <template #header>
        <div class="section-head">
          <span>服务列表</span>
          <el-tag>{{ servers.length }} 个服务</el-tag>
        </div>
      </template>
      <el-empty v-if="!servers.length" description="暂无 MCP 服务" :image-size="84">
        <el-button type="primary" @click="openCreateDialog">创建第一个服务</el-button>
      </el-empty>
      <el-table v-else :data="servers" row-key="server_name">
        <el-table-column label="服务" min-width="220">
          <template #default="{ row }">
            <div class="name-cell">
              <strong>{{ row.display_name || row.server_name }}</strong>
              <code>{{ row.server_name }}</code>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="150">
          <template #default="{ row }">
            <el-tag :type="row.transport === 'stdio' ? 'warning' : 'success'">
              {{ row.transport === 'stdio' ? 'stdio' : 'streamable_http' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="入口" min-width="260">
          <template #default="{ row }">
            <span class="mono">{{ row.transport === 'stdio' ? row.command || '-' : row.url || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工具数" width="90" prop="tool_count" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.last_status === 'error' ? 'danger' : row.last_status === 'ok' ? 'success' : 'info'">
              {{ row.last_status || '未测试' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="仅管理员" width="100">
          <template #default="{ row }">{{ row.admin_only ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch :model-value="Boolean(row.is_enabled)" @change="toggleServer(row, $event)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button size="small" :loading="testingName === row.server_name" @click="testServer(row)">
                测试
              </el-button>
              <el-button size="small" :loading="refreshingName === row.server_name" @click="refreshTools(row)">
                刷新工具
              </el-button>
              <el-button size="small" :icon="EditPen" @click="openEditDialog(row)">编辑</el-button>
              <el-button size="small" type="danger" :icon="Delete" @click="deleteServer(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="page-card">
      <template #header>
        <div class="section-head">
          <span>工具缓存</span>
          <div class="tool-filter">
            <el-select v-model="selectedServer" clearable placeholder="全部服务" style="width: 180px" @change="loadTools">
              <el-option
                v-for="server in servers"
                :key="server.server_name"
                :label="server.display_name || server.server_name"
                :value="server.server_name"
              />
            </el-select>
            <el-tag>{{ tools.length }} 个工具</el-tag>
          </div>
        </div>
      </template>
      <el-empty v-if="!tools.length" description="暂无 MCP 工具缓存" :image-size="84" />
      <el-table v-else :data="tools" row-key="exposed_tool_name">
        <el-table-column label="暴露工具名" min-width="240">
          <template #default="{ row }">
            <div class="name-cell">
              <strong>{{ row.display_name || row.original_tool_name }}</strong>
              <code>{{ row.exposed_tool_name }}</code>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="服务" width="140" prop="server_name" />
        <el-table-column label="原始工具" width="180" prop="original_tool_name" />
        <el-table-column label="描述" min-width="260">
          <template #default="{ row }">
            <span class="desc-text">{{ row.description || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="仅管理员" width="110">
          <template #default="{ row }">
            <el-switch
              :model-value="Boolean(row.admin_only)"
              :disabled="!Boolean(row.server_enabled)"
              @change="toggleTool(row, { admin_only: $event })"
            />
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="Boolean(row.is_enabled) && Boolean(row.server_enabled)"
              :disabled="!Boolean(row.server_enabled)"
              @change="toggleTool(row, { is_enabled: $event })"
            />
          </template>
        </el-table-column>
        <el-table-column label="发现时间" width="180" prop="last_seen_at" />
      </el-table>
    </el-card>

    <el-card class="page-card">
      <template #header>
        <div class="section-head">
          <span>调用日志</span>
          <div class="tool-filter">
            <el-select v-model="logFilters.server_name" clearable placeholder="全部服务" style="width: 160px" @change="loadCallLogs">
              <el-option
                v-for="server in servers"
                :key="server.server_name"
                :label="server.display_name || server.server_name"
                :value="server.server_name"
              />
            </el-select>
            <el-select v-model="logFilters.is_success" placeholder="全部状态" style="width: 120px" @change="loadCallLogs">
              <el-option label="全部状态" value="" />
              <el-option label="成功" value="true" />
              <el-option label="失败" value="false" />
            </el-select>
            <el-button :icon="Refresh" :loading="logLoading" @click="loadCallLogs">刷新</el-button>
          </div>
        </div>
      </template>
      <el-empty v-if="!callLogs.length" description="暂无 MCP 调用日志" :image-size="84" />
      <template v-else>
        <el-table :data="callLogs" row-key="id">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="log-detail">
                <div>
                  <strong>参数</strong>
                  <pre>{{ formatJson(row.arguments_json) }}</pre>
                </div>
                <div>
                  <strong>{{ row.is_success ? '返回摘要' : '错误' }}</strong>
                  <pre>{{ row.is_success ? row.result_excerpt || '-' : row.error_text || '-' }}</pre>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="180" prop="created_at" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_success ? 'success' : 'danger'">
                {{ row.is_success ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="服务" width="130" prop="server_name" />
          <el-table-column label="工具" min-width="220">
            <template #default="{ row }">
              <div class="name-cell">
                <strong>{{ row.original_tool_name }}</strong>
                <code>{{ row.exposed_tool_name }}</code>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="会话" width="160">
            <template #default="{ row }">
              <span class="mono">{{ row.session_type }}:{{ row.session_id }}</span>
            </template>
          </el-table-column>
          <el-table-column label="用户" width="120" prop="user_id" />
          <el-table-column label="耗时" width="90">
            <template #default="{ row }">{{ row.latency_ms ?? '-' }} ms</template>
          </el-table-column>
        </el-table>
        <div class="pager-row">
          <el-pagination
            v-model:current-page="logPage"
            v-model:page-size="logPageSize"
            background
            layout="total, sizes, prev, pager, next"
            :total="logTotal"
            :page-sizes="[10, 20, 50, 100]"
            @current-change="loadCallLogs"
            @size-change="handleLogPageSizeChange"
          />
        </div>
      </template>
    </el-card>

    <el-dialog v-model="downloadDialogVisible" width="680px" class="mcp-dialog">
      <template #header>
        <div class="dialog-head">
          <h3>下载 MCP</h3>
          <el-tag type="info">npm</el-tag>
        </div>
      </template>
      <div class="download-panel">
        <el-form label-position="top">
          <el-form-item label="手动输入 npm 包名">
            <div class="download-input-row">
              <el-input
                v-model="downloadForm.package_name"
                placeholder="例如 @modelcontextprotocol/server-memory"
                @keyup.enter="downloadManualPackage"
              />
              <el-button
                type="primary"
                :icon="Download"
                :loading="downloadingName === downloadForm.package_name.trim()"
                @click="downloadManualPackage"
              >
                下载
              </el-button>
            </div>
          </el-form-item>
        </el-form>

        <div class="download-section-title">推荐 MCP</div>
        <div class="download-grid">
          <div v-for="item in npmDownloadRecommendations" :key="item.package_name" class="download-item">
            <div>
              <strong>{{ item.display_name }}</strong>
              <span>{{ item.summary }}</span>
              <code>{{ item.package_name }}</code>
            </div>
            <div class="download-actions">
              <el-button
                size="small"
                :icon="Download"
                :loading="downloadingName === item.package_name"
                @click="downloadNpmPackage(item.package_name)"
              >
                下载
              </el-button>
              <el-button size="small" @click="fillPresetFromDownload(item.preset_name)">填配置</el-button>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="dialogVisible" width="760px" class="mcp-dialog">
      <template #header>
        <div class="dialog-head">
          <h3>{{ dialogMode === 'create' ? '新增 MCP 服务' : '编辑 MCP 服务' }}</h3>
          <el-tag>{{ form.transport }}</el-tag>
        </div>
      </template>
      <el-form :model="form" label-position="top" class="mcp-form">
        <div class="form-grid">
          <el-form-item label="服务名">
            <el-input v-model="form.server_name" :disabled="dialogMode === 'edit'" placeholder="例如 filesystem" />
          </el-form-item>
          <el-form-item label="显示名称">
            <el-input v-model="form.display_name" placeholder="例如 文件系统" />
          </el-form-item>
          <el-form-item label="传输类型">
            <el-segmented
              v-model="form.transport"
              :options="[
                { label: 'stdio', value: 'stdio' },
                { label: 'HTTP', value: 'streamable_http' },
              ]"
            />
          </el-form-item>
          <el-form-item label="超时秒数">
            <el-input-number v-model="form.timeout_seconds" :min="1" :max="120" />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.is_enabled" />
          </el-form-item>
          <el-form-item label="仅管理员可用">
            <el-switch v-model="form.admin_only" />
          </el-form-item>
        </div>

        <section v-if="form.transport === 'stdio'" class="config-section">
          <el-form-item label="Command">
            <el-input v-model="form.command" placeholder="例如 npx" />
          </el-form-item>
          <el-form-item label="Args JSON">
            <el-input v-model="form.args_text" type="textarea" :rows="4" placeholder='["-y", "@modelcontextprotocol/server-everything"]' />
          </el-form-item>
          <el-form-item label="Env JSON">
            <el-input v-model="form.env_text" type="textarea" :rows="3" placeholder='{"TOKEN": "xxx"}' />
          </el-form-item>
        </section>

        <section v-else class="config-section">
          <el-form-item label="URL">
            <el-input v-model="form.url" placeholder="http://127.0.0.1:8000/mcp" />
          </el-form-item>
          <el-form-item label="Headers JSON">
            <el-input v-model="form.headers_text" type="textarea" :rows="4" placeholder='{"Authorization": "Bearer xxx"}' />
          </el-form-item>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button :loading="saving" @click="saveAndTestServer">保存并测试</el-button>
        <el-button type="primary" :loading="saving" @click="saveServer">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Download, EditPen, Plus, Refresh } from '@element-plus/icons-vue'

import { adminApi } from '../api/admin'

interface McpServer {
  server_name: string
  display_name?: string
  transport: 'stdio' | 'streamable_http'
  command?: string
  args_json?: unknown[]
  env_json?: Record<string, unknown>
  url?: string
  headers_json?: Record<string, unknown>
  timeout_seconds: number
  is_enabled: boolean | number
  admin_only: boolean | number
  last_status?: string
  last_error?: string
  tool_count?: number
}

interface McpTool {
  exposed_tool_name: string
  original_tool_name: string
  server_name: string
  display_name?: string
  description?: string
  is_enabled: boolean | number
  admin_only: boolean | number
  server_enabled?: boolean | number
  server_admin_only?: boolean | number
}

interface McpToolCallLog {
  id: number
  session_type: string
  session_id: number
  user_id?: number
  server_name: string
  exposed_tool_name: string
  original_tool_name: string
  arguments_json?: unknown
  result_excerpt?: string
  error_text?: string
  is_success: boolean | number
  latency_ms?: number
  created_at?: string
}

interface McpPreset {
  server_name: string
  display_name: string
  summary: string
  transport: 'stdio'
  command: string
  args_json: string[]
  env_json: Record<string, string>
}

interface McpDownloadRecommendation {
  display_name: string
  summary: string
  package_name: string
  preset_name: string
}

const mcpPresets: McpPreset[] = [
  {
    server_name: 'filesystem',
    display_name: '文件系统',
    summary: '只把指定目录开放给模型，适合读项目文档、配置样例和日志',
    transport: 'stdio',
    command: 'npx',
    args_json: ['-y', '@modelcontextprotocol/server-filesystem', '/app'],
    env_json: {},
  },
  {
    server_name: 'memory',
    display_name: '长期记忆',
    summary: '结构化保存事实和关系，适合做可查询的知识记忆',
    transport: 'stdio',
    command: 'npx',
    args_json: ['-y', '@modelcontextprotocol/server-memory'],
    env_json: {},
  },
  {
    server_name: 'thinking',
    display_name: '步骤思考',
    summary: '给复杂问题提供分步推理工具，适合规划和排障',
    transport: 'stdio',
    command: 'npx',
    args_json: ['-y', '@modelcontextprotocol/server-sequential-thinking'],
    env_json: {},
  },
  {
    server_name: 'git',
    display_name: 'Git 仓库',
    summary: '读取仓库状态、提交和变更，适合让猫娘回答项目代码问题',
    transport: 'stdio',
    command: 'uvx',
    args_json: ['mcp-server-git', '--repository', '/app'],
    env_json: {},
  },
]

const npmDownloadRecommendations: McpDownloadRecommendation[] = [
  {
    display_name: '长期记忆',
    summary: '保存实体、关系和事实，适合做长期上下文',
    package_name: '@modelcontextprotocol/server-memory',
    preset_name: 'memory',
  },
  {
    display_name: '步骤思考',
    summary: '复杂问题拆步分析，适合规划和排障',
    package_name: '@modelcontextprotocol/server-sequential-thinking',
    preset_name: 'thinking',
  },
  {
    display_name: '文件系统',
    summary: '读取指定目录文件，适合管理员受控使用',
    package_name: '@modelcontextprotocol/server-filesystem',
    preset_name: 'filesystem',
  },
]

const servers = ref<McpServer[]>([])
const tools = ref<McpTool[]>([])
const callLogs = ref<McpToolCallLog[]>([])
const loading = ref(false)
const logLoading = ref(false)
const saving = ref(false)
const testingName = ref('')
const refreshingName = ref('')
const installingName = ref('')
const downloadingName = ref('')
const selectedServer = ref('')
const logPage = ref(1)
const logPageSize = ref(20)
const logTotal = ref(0)
const logFilters = reactive({
  server_name: '',
  is_success: '',
})
const dialogVisible = ref(false)
const downloadDialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')

const downloadForm = reactive({
  package_name: '',
})

const form = reactive({
  server_name: '',
  display_name: '',
  transport: 'stdio' as 'stdio' | 'streamable_http',
  command: '',
  args_text: '[]',
  env_text: '{}',
  url: '',
  headers_text: '{}',
  timeout_seconds: 15,
  is_enabled: true,
  admin_only: true,
})

const parseJson = (text: string, fallback: unknown) => {
  const raw = text.trim()
  if (!raw) return fallback
  return JSON.parse(raw)
}

const resetForm = () => {
  form.server_name = ''
  form.display_name = ''
  form.transport = 'stdio'
  form.command = ''
  form.args_text = '[]'
  form.env_text = '{}'
  form.url = ''
  form.headers_text = '{}'
  form.timeout_seconds = 15
  form.is_enabled = true
  form.admin_only = true
}

const loadServers = async () => {
  const data = await adminApi.getMcpServers()
  servers.value = data.items || []
}

const loadTools = async () => {
  const data = await adminApi.getMcpTools({ server_name: selectedServer.value })
  tools.value = data.items || []
}

const loadCallLogs = async () => {
  logLoading.value = true
  try {
    const data = await adminApi.getMcpToolCallLogs({
      page: logPage.value,
      page_size: logPageSize.value,
      server_name: logFilters.server_name,
      is_success: logFilters.is_success,
    })
    callLogs.value = data.items || []
    logTotal.value = data.total || 0
  } finally {
    logLoading.value = false
  }
}

const loadData = async () => {
  loading.value = true
  try {
    await loadServers()
    await loadTools()
    await loadCallLogs()
  } finally {
    loading.value = false
  }
}

const handleLogPageSizeChange = () => {
  logPage.value = 1
  loadCallLogs()
}

const formatJson = (value: unknown) => JSON.stringify(value ?? {}, null, 2)

const openDownloadDialog = () => {
  downloadForm.package_name = ''
  downloadDialogVisible.value = true
}

const openCreateDialog = () => {
  dialogMode.value = 'create'
  resetForm()
  dialogVisible.value = true
}

const openPresetDialog = (preset: McpPreset) => {
  dialogMode.value = 'create'
  resetForm()
  form.server_name = preset.server_name
  form.display_name = preset.display_name
  form.transport = preset.transport
  form.command = preset.command
  form.args_text = JSON.stringify(preset.args_json, null, 2)
  form.env_text = JSON.stringify(preset.env_json, null, 2)
  form.timeout_seconds = 20
  form.is_enabled = false
  form.admin_only = true
  dialogVisible.value = true
}

const presetInstalled = (preset: McpPreset) =>
  servers.value.some((server) => server.server_name === preset.server_name)

const downloadNpmPackage = async (packageName: string) => {
  const cleaned = packageName.trim()
  if (!cleaned) {
    ElMessage.warning('请输入 npm 包名')
    return
  }
  downloadingName.value = cleaned
  try {
    await adminApi.downloadMcpNpmPackage({ package_name: cleaned })
    ElMessage.success('下载完成，可以填配置后测试接入')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '下载失败')
  } finally {
    downloadingName.value = ''
  }
}

const downloadManualPackage = () => downloadNpmPackage(downloadForm.package_name)

const fillPresetFromDownload = (presetName: string) => {
  const preset = mcpPresets.find((item) => item.server_name === presetName)
  if (!preset) return
  downloadDialogVisible.value = false
  openPresetDialog(preset)
}

const installPreset = async (preset: McpPreset) => {
  installingName.value = preset.server_name
  try {
    const result = await adminApi.installMcpPreset(preset.server_name)
    const count = result?.refresh?.refreshed_count || result?.refresh?.tool_count || 0
    ElMessage.success(`安装完成，已缓存 ${count} 个工具`)
    await loadData()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '安装失败')
  } finally {
    installingName.value = ''
  }
}

const openEditDialog = (row: McpServer) => {
  dialogMode.value = 'edit'
  form.server_name = row.server_name
  form.display_name = row.display_name || ''
  form.transport = row.transport === 'streamable_http' ? 'streamable_http' : 'stdio'
  form.command = row.command || ''
  form.args_text = JSON.stringify(row.args_json || [], null, 2)
  form.env_text = JSON.stringify(row.env_json || {}, null, 2)
  form.url = row.url || ''
  form.headers_text = JSON.stringify(row.headers_json || {}, null, 2)
  form.timeout_seconds = Number(row.timeout_seconds || 15)
  form.is_enabled = Boolean(row.is_enabled)
  form.admin_only = Boolean(row.admin_only)
  dialogVisible.value = true
}

const buildPayload = () => {
  const payload: Record<string, unknown> = {
    display_name: form.display_name.trim() || undefined,
    transport: form.transport,
    timeout_seconds: form.timeout_seconds,
    is_enabled: form.is_enabled,
    admin_only: form.admin_only,
  }
  if (dialogMode.value === 'create') payload.server_name = form.server_name.trim()
  if (form.transport === 'stdio') {
    payload.command = form.command.trim()
    payload.args_json = parseJson(form.args_text, [])
    payload.env_json = parseJson(form.env_text, {})
    payload.url = ''
    payload.headers_json = {}
  } else {
    payload.url = form.url.trim()
    payload.headers_json = parseJson(form.headers_text, {})
    payload.command = ''
    payload.args_json = []
    payload.env_json = {}
  }
  return payload
}

const persistServer = async () => {
  const payload = buildPayload()
  if (dialogMode.value === 'create') {
    await adminApi.createMcpServer(payload)
  } else {
    await adminApi.updateMcpServer(form.server_name, payload)
  }
  return form.server_name
}

const saveServer = async () => {
  saving.value = true
  try {
    await persistServer()
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadData()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const saveAndTestServer = async () => {
  saving.value = true
  try {
    const serverName = await persistServer()
    dialogVisible.value = false
    await loadData()
    testingName.value = serverName
    const result = await adminApi.testMcpServer(serverName)
    ElMessage.success(`连接成功，发现 ${result.tool_count || 0} 个工具`)
    await loadServers()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '测试失败')
  } finally {
    saving.value = false
    testingName.value = ''
  }
}

const toggleServer = async (row: McpServer, value: string | number | boolean) => {
  await adminApi.updateMcpServer(row.server_name, { is_enabled: Boolean(value) })
  await loadData()
}

const testServer = async (row: McpServer) => {
  testingName.value = row.server_name
  try {
    const result = await adminApi.testMcpServer(row.server_name)
    ElMessage.success(`连接成功，发现 ${result.tool_count || 0} 个工具`)
    await loadServers()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '测试失败')
  } finally {
    testingName.value = ''
  }
}

const refreshTools = async (row: McpServer) => {
  refreshingName.value = row.server_name
  try {
    const result = await adminApi.refreshMcpTools(row.server_name)
    ElMessage.success(`刷新完成，缓存 ${result.refreshed_count || 0} 个工具`)
    await loadData()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '刷新失败')
  } finally {
    refreshingName.value = ''
  }
}

const deleteServer = async (row: McpServer) => {
  await ElMessageBox.confirm(`确定删除 MCP 服务 ${row.server_name} 吗？`, '删除确认', { type: 'warning' })
  await adminApi.deleteMcpServer(row.server_name)
  ElMessage.success('已删除')
  await loadData()
}

const toggleTool = async (row: McpTool, payload: Record<string, unknown>) => {
  await adminApi.updateMcpTool(row.exposed_tool_name, payload)
  await loadTools()
}

onMounted(loadData)
</script>

<style scoped>
.mcp-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.header-actions,
.section-head,
.tool-filter,
.row-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preset-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.preset-item {
  align-items: flex-start;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  color: #0f172a;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 132px;
  padding: 14px;
  text-align: left;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.preset-item:hover {
  border-color: #409eff;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
  transform: translateY(-1px);
}

.preset-item span {
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.preset-item code {
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.preset-actions {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  margin-top: auto;
  width: 100%;
}

.download-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.download-input-row {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(0, 1fr) auto;
  width: 100%;
}

.download-section-title {
  color: #0f172a;
  font-weight: 700;
}

.download-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: 1fr;
}

.download-item {
  align-items: center;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) auto;
  padding: 12px;
}

.download-item > div:first-child {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.download-item span {
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.download-item code {
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.download-actions {
  display: flex;
  gap: 8px;
}

.section-head {
  justify-content: space-between;
}

.name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.name-cell code,
.mono {
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.desc-text {
  display: block;
  color: #64748b;
  line-height: 1.5;
  max-height: 72px;
  overflow: auto;
}

.log-detail {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 8px 24px 12px;
}

.log-detail pre {
  background: #0f172a;
  border-radius: 8px;
  color: #e2e8f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  margin: 8px 0 0;
  max-height: 260px;
  overflow: auto;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.pager-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dialog-head h3 {
  margin: 0;
}

.mcp-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.config-section {
  border-top: 1px solid #e2e8f0;
  padding-top: 14px;
}

@media (max-width: 760px) {
  .preset-grid {
    grid-template-columns: 1fr;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .log-detail {
    grid-template-columns: 1fr;
  }

  .header-actions,
  .section-head,
  .download-item,
  .download-input-row {
    align-items: stretch;
    flex-direction: column;
    grid-template-columns: 1fr;
  }

  .download-actions {
    justify-content: flex-start;
  }
}
</style>
