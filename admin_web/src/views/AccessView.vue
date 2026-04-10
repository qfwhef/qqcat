<template>
  <div>
    <div class="page-header">
      <div class="page-title">访问控制</div>
      <div style="display: flex; gap: 10px">
        <el-button :loading="loading" @click="loadData">刷新</el-button>
        <el-button type="primary" @click="openAdminDialog()">新增管理员</el-button>
      </div>
    </div>

    <div class="split-grid">
      <el-card class="page-card">
        <template #header>
          <span>管理员白名单</span>
        </template>
        <el-table :data="adminUsers">
          <el-table-column prop="user_id" label="QQ 号" min-width="120" />
          <el-table-column prop="nickname" label="昵称" min-width="140" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" min-width="160" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" @click="openAdminDialog(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card class="page-card">
        <template #header>应用级密钥</template>
        <el-table :data="secrets">
          <el-table-column prop="secret_key" label="键名" min-width="180" />
          <el-table-column prop="value_hint" label="说明" min-width="160" />
          <el-table-column prop="masked_value" label="当前值" min-width="140" />
          <el-table-column prop="source" label="来源" width="90" />
          <el-table-column prop="updated_at" label="更新时间" min-width="160" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" @click="openSecretDialog(row)">更新</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <el-dialog v-model="adminDialogVisible" :title="adminDialogMode === 'create' ? '新增管理员' : '编辑管理员'" width="420px">
      <el-form label-position="top" :model="adminForm">
        <el-form-item label="QQ 号">
          <el-input v-model.number="adminForm.user_id" :disabled="adminDialogMode === 'edit'" type="number" />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="adminForm.nickname" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="adminForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adminDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="adminSaving" @click="saveAdminUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="secretDialogVisible" :title="`更新密钥: ${secretForm.secret_key}`" width="460px">
      <el-form label-position="top" :model="secretForm">
        <el-form-item label="密钥说明">
          <el-input v-model="secretForm.value_hint" />
        </el-form-item>
        <el-form-item label="新密钥值">
          <el-input v-model="secretForm.secret_value" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="secretDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="secretSaving" @click="saveSecret">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminApi } from '../api/admin'

const loading = ref(false)
const adminSaving = ref(false)
const secretSaving = ref(false)
const adminUsers = ref<any[]>([])
const secrets = ref<any[]>([])
const adminDialogVisible = ref(false)
const adminDialogMode = ref<'create' | 'edit'>('create')
const secretDialogVisible = ref(false)
const adminForm = reactive({
  user_id: undefined as number | undefined,
  nickname: '',
  is_active: true,
})
const secretForm = reactive({
  secret_key: '',
  value_hint: '',
  secret_value: '',
})

const loadData = async () => {
  loading.value = true
  try {
    const [adminRes, secretRes] = await Promise.all([adminApi.getAdminUsers(), adminApi.getSecrets()])
    adminUsers.value = adminRes.items || []
    secrets.value = secretRes.items || []
  } finally {
    loading.value = false
  }
}

const openAdminDialog = (row?: any) => {
  adminDialogMode.value = row ? 'edit' : 'create'
  adminForm.user_id = row?.user_id
  adminForm.nickname = row?.nickname || ''
  adminForm.is_active = row ? Boolean(row.is_active) : true
  adminDialogVisible.value = true
}

const saveAdminUser = async () => {
  if (!adminForm.user_id) {
    ElMessage.warning('请填写管理员 QQ 号')
    return
  }
  adminSaving.value = true
  try {
    if (adminDialogMode.value === 'create') {
      await adminApi.createAdminUser({
        user_id: adminForm.user_id,
        nickname: adminForm.nickname,
        is_active: adminForm.is_active,
      })
    } else {
      await adminApi.updateAdminUser(adminForm.user_id, {
        nickname: adminForm.nickname,
        is_active: adminForm.is_active,
      })
    }
    ElMessage.success('管理员白名单已更新')
    adminDialogVisible.value = false
    await loadData()
  } finally {
    adminSaving.value = false
  }
}

const openSecretDialog = (row: any) => {
  secretForm.secret_key = row.secret_key
  secretForm.value_hint = row.value_hint || ''
  secretForm.secret_value = ''
  secretDialogVisible.value = true
}

const saveSecret = async () => {
  if (!secretForm.secret_key || !secretForm.secret_value.trim()) {
    ElMessage.warning('请输入新的密钥值')
    return
  }
  secretSaving.value = true
  try {
    await adminApi.updateSecret(secretForm.secret_key, {
      secret_value: secretForm.secret_value.trim(),
      value_hint: secretForm.value_hint || undefined,
    })
    ElMessage.success('密钥已更新')
    secretDialogVisible.value = false
    await loadData()
  } finally {
    secretSaving.value = false
  }
}

onMounted(loadData)
</script>
