<template>
  <div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="群聊配置" name="group">
        <el-card class="page-card">
          <div class="table-toolbar">
            <div style="font-size: 16px; font-weight: 700; color: #111827">群聊配置</div>
          </div>
          <div class="table-toolbar">
            <el-input v-model="groupKeyword" placeholder="搜索群号或群名" style="width: 260px" clearable @keyup.enter="loadGroupConfigs" />
            <el-button type="primary" @click="loadGroupConfigs">查询</el-button>
          </div>
          <el-table :data="groupConfigs.items">
            <el-table-column prop="group_id" label="群号" min-width="120" />
            <el-table-column prop="group_name" label="群名" min-width="140" />
            <el-table-column prop="reply_rate" label="回复率" width="100" />
            <el-table-column label="睡眠" width="90">
              <template #default="{ row }">{{ row.is_sleeping ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column label="AI" width="90">
              <template #default="{ row }">{{ row.enable_ai ? '开' : '关' }}</template>
            </el-table-column>
            <el-table-column label="摘要" width="90">
              <template #default="{ row }">{{ row.enable_summary ? '开' : '关' }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" min-width="160" />
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button link type="primary" @click="openGroupDialog(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="display: flex; justify-content: flex-end; margin-top: 16px">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="groupConfigs.total"
              :page-size="groupConfigs.page_size"
              :current-page="groupConfigs.page"
              @current-change="handleGroupPageChange"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="私聊配置" name="private">
        <el-card class="page-card">
          <div class="table-toolbar">
            <div style="font-size: 16px; font-weight: 700; color: #111827">私聊配置</div>
          </div>
          <div class="table-toolbar">
            <el-input v-model="privateKeyword" placeholder="搜索 QQ 或昵称" style="width: 260px" clearable @keyup.enter="loadPrivateConfigs" />
            <el-button type="primary" @click="loadPrivateConfigs">查询</el-button>
          </div>
          <el-table :data="privateConfigs.items">
            <el-table-column prop="user_id" label="用户 QQ" min-width="120" />
            <el-table-column prop="user_nickname" label="昵称" min-width="140" />
            <el-table-column prop="reply_rate" label="回复率" width="100" />
            <el-table-column label="睡眠" width="90">
              <template #default="{ row }">{{ row.is_sleeping ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column label="AI" width="90">
              <template #default="{ row }">{{ row.enable_ai ? '开' : '关' }}</template>
            </el-table-column>
            <el-table-column label="摘要" width="90">
              <template #default="{ row }">{{ row.enable_summary ? '开' : '关' }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="更新时间" min-width="160" />
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button link type="primary" @click="openPrivateDialog(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="display: flex; justify-content: flex-end; margin-top: 16px">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="privateConfigs.total"
              :page-size="privateConfigs.page_size"
              :current-page="privateConfigs.page"
              @current-change="handlePrivatePageChange"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-card class="page-card" style="margin-top: 20px">
      <template #header>
        <div class="table-toolbar" style="margin-bottom: 0">
          <span>黑名单</span>
          <div style="display: flex; gap: 10px">
            <el-button :loading="loading" @click="loadAll">刷新</el-button>
            <el-button type="primary" :loading="blocklistSaving" @click="saveBlocklist">保存黑名单</el-button>
          </div>
        </div>
      </template>
      <div class="split-grid">
        <el-form label-position="top">
          <el-form-item label="黑名单群号">
            <el-input v-model="blockedGroupsRaw" type="textarea" :rows="6" placeholder="每行一个群号，也支持逗号分隔" />
          </el-form-item>
        </el-form>
        <el-form label-position="top">
          <el-form-item label="黑名单用户 QQ">
            <el-input v-model="blockedUsersRaw" type="textarea" :rows="6" placeholder="每行一个用户 QQ，也支持逗号分隔" />
          </el-form-item>
        </el-form>
      </div>
    </el-card>

    <el-dialog v-model="groupDialogVisible" title="编辑群聊配置" width="460px">
      <el-form label-position="top" :model="groupForm">
        <el-form-item label="群号">
          <el-input v-model.number="groupForm.group_id" disabled />
        </el-form-item>
        <el-form-item label="群名">
          <el-input v-model="groupForm.group_name" />
        </el-form-item>
        <el-form-item label="回复率">
          <el-input-number v-model="groupForm.reply_rate" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="功能开关">
          <div style="display: grid; gap: 12px">
            <el-switch v-model="groupForm.is_sleeping" active-text="睡眠模式" />
            <el-switch v-model="groupForm.enable_ai" active-text="启用 AI" />
            <el-switch v-model="groupForm.enable_summary" active-text="启用摘要" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="groupSaving" @click="saveGroupConfig">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="privateDialogVisible" title="编辑私聊配置" width="460px">
      <el-form label-position="top" :model="privateForm">
        <el-form-item label="用户 QQ">
          <el-input v-model.number="privateForm.user_id" disabled />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="privateForm.user_nickname" />
        </el-form-item>
        <el-form-item label="回复率">
          <el-input-number v-model="privateForm.reply_rate" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="功能开关">
          <div style="display: grid; gap: 12px">
            <el-switch v-model="privateForm.is_sleeping" active-text="睡眠模式" />
            <el-switch v-model="privateForm.enable_ai" active-text="启用 AI" />
            <el-switch v-model="privateForm.enable_summary" active-text="启用摘要" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="privateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="privateSaving" @click="savePrivateConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminApi } from '../api/admin'

const loading = ref(false)
const blocklistSaving = ref(false)
const groupSaving = ref(false)
const privateSaving = ref(false)
const activeTab = ref<'group' | 'private'>('group')
const blockedGroupsRaw = ref('')
const blockedUsersRaw = ref('')
const groupKeyword = ref('')
const privateKeyword = ref('')
const groupDialogVisible = ref(false)
const privateDialogVisible = ref(false)
const groupConfigs = reactive({ items: [] as any[], page: 1, page_size: 10, total: 0 })
const privateConfigs = reactive({ items: [] as any[], page: 1, page_size: 10, total: 0 })
const groupForm = reactive({
  group_id: undefined as number | undefined,
  group_name: '',
  reply_rate: 100,
  is_sleeping: false,
  enable_ai: true,
  enable_summary: true,
})
const privateForm = reactive({
  user_id: undefined as number | undefined,
  user_nickname: '',
  reply_rate: 100,
  is_sleeping: false,
  enable_ai: true,
  enable_summary: true,
})

const parseNumberList = (raw: string) =>
  raw
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item))

const loadBlocklist = async () => {
  const data = await adminApi.getBlocklist()
  blockedGroupsRaw.value = (data.blocked_groups || []).join('\n')
  blockedUsersRaw.value = (data.blocked_users || []).join('\n')
}

const loadGroupConfigs = async () => {
  const data = await adminApi.getGroupConfigs({
    page: groupConfigs.page,
    page_size: groupConfigs.page_size,
    keyword: groupKeyword.value,
  })
  Object.assign(groupConfigs, data)
}

const loadPrivateConfigs = async () => {
  const data = await adminApi.getPrivateConfigs({
    page: privateConfigs.page,
    page_size: privateConfigs.page_size,
    keyword: privateKeyword.value,
  })
  Object.assign(privateConfigs, data)
}

const loadAll = async () => {
  loading.value = true
  try {
    await Promise.all([loadBlocklist(), loadGroupConfigs(), loadPrivateConfigs()])
  } finally {
    loading.value = false
  }
}

const saveBlocklist = async () => {
  blocklistSaving.value = true
  try {
    await adminApi.updateBlocklist({
      blocked_groups: parseNumberList(blockedGroupsRaw.value),
      blocked_users: parseNumberList(blockedUsersRaw.value),
    })
    ElMessage.success('黑名单已更新')
    await loadBlocklist()
  } finally {
    blocklistSaving.value = false
  }
}

const openGroupDialog = (row: any) => {
  groupForm.group_id = row.group_id
  groupForm.group_name = row.group_name || ''
  groupForm.reply_rate = Number(row.reply_rate || 100)
  groupForm.is_sleeping = Boolean(row.is_sleeping)
  groupForm.enable_ai = Boolean(row.enable_ai)
  groupForm.enable_summary = Boolean(row.enable_summary)
  groupDialogVisible.value = true
}

const saveGroupConfig = async () => {
  if (!groupForm.group_id) {
    return
  }
  groupSaving.value = true
  try {
    await adminApi.updateGroupConfig(groupForm.group_id, {
      group_name: groupForm.group_name,
      reply_rate: groupForm.reply_rate,
      is_sleeping: groupForm.is_sleeping,
      enable_ai: groupForm.enable_ai,
      enable_summary: groupForm.enable_summary,
    })
    ElMessage.success('群聊配置已更新')
    groupDialogVisible.value = false
    await loadGroupConfigs()
  } finally {
    groupSaving.value = false
  }
}

const openPrivateDialog = (row: any) => {
  privateForm.user_id = row.user_id
  privateForm.user_nickname = row.user_nickname || ''
  privateForm.reply_rate = Number(row.reply_rate || 100)
  privateForm.is_sleeping = Boolean(row.is_sleeping)
  privateForm.enable_ai = Boolean(row.enable_ai)
  privateForm.enable_summary = Boolean(row.enable_summary)
  privateDialogVisible.value = true
}

const savePrivateConfig = async () => {
  if (!privateForm.user_id) {
    return
  }
  privateSaving.value = true
  try {
    await adminApi.updatePrivateConfig(privateForm.user_id, {
      user_nickname: privateForm.user_nickname,
      reply_rate: privateForm.reply_rate,
      is_sleeping: privateForm.is_sleeping,
      enable_ai: privateForm.enable_ai,
      enable_summary: privateForm.enable_summary,
    })
    ElMessage.success('私聊配置已更新')
    privateDialogVisible.value = false
    await loadPrivateConfigs()
  } finally {
    privateSaving.value = false
  }
}

const handleGroupPageChange = async (page: number) => {
  groupConfigs.page = page
  await loadGroupConfigs()
}

const handlePrivatePageChange = async (page: number) => {
  privateConfigs.page = page
  await loadPrivateConfigs()
}

onMounted(loadAll)
</script>
