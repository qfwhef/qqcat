<template>
  <div>
    <el-card class="page-card">
      <div class="table-toolbar" style="margin-bottom: 8px">
        <div style="font-size: 16px; font-weight: 700; color: #111827">会话管理</div>
      </div>

      <el-tabs v-model="activeTab" @tab-change="loadData">
        <el-tab-pane label="群聊会话" name="group" />
        <el-tab-pane label="私聊会话" name="private" />
      </el-tabs>

      <el-form :inline="true" class="toolbar-form compact-filter-form">
        <el-form-item label="关键词">
          <el-input v-model="keyword" placeholder="群名 / QQ昵称 / ID" clearable style="width: 240px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadData">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows">
        <el-table-column prop="display_name" label="群名 / QQ昵称" min-width="180" />
        <el-table-column prop="session_id" label="群号 / QQ号" min-width="140" />
        <el-table-column prop="total_messages" label="消息数" width="100" />
        <el-table-column prop="last_message_id" label="最后消息ID" min-width="120" />
        <el-table-column prop="last_message_at" label="最后消息时间" min-width="160" />
        <el-table-column prop="updated_at" label="更新时间" min-width="160" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminApi } from '../api/admin'

const activeTab = ref<'group' | 'private'>('group')
const loading = ref(false)
const keyword = ref('')
const rows = ref<any[]>([])

const emitSessionsUpdated = () => {
  window.dispatchEvent(new CustomEvent('message-sessions-updated'))
}

const loadData = async () => {
  loading.value = true
  try {
    const data =
      activeTab.value === 'group'
        ? await adminApi.getGroupMessageSessions({ keyword: keyword.value })
        : await adminApi.getPrivateMessageSessions({ keyword: keyword.value })
    rows.value = data.items || []
  } finally {
    loading.value = false
  }
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(
    `确认删除当前会话 ${row.display_name} 吗？这会同时删除聊天记录、摘要、会话状态和 AI 调用日志。`,
    '删除会话',
    { type: 'warning' },
  )
  if (activeTab.value === 'group') {
    await adminApi.deleteGroupMessageSession(Number(row.session_id))
  } else {
    await adminApi.deletePrivateMessageSession(Number(row.session_id))
  }
  ElMessage.success('会话已删除')
  emitSessionsUpdated()
  await loadData()
}

onMounted(loadData)
</script>
