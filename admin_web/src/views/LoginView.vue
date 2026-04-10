<template>
  <div class="login-shell">
    <el-card class="login-card">
      <div class="login-title">小喵机器人管理后台</div>
      <div class="login-subtitle">使用管理员 QQ 白名单和后台令牌登录</div>
      <el-form label-position="top" :model="form" @submit.prevent="handleLogin">
        <el-form-item label="QQ 号">
          <el-input v-model.number="form.qq" type="number" placeholder="输入管理员 QQ 号" />
        </el-form-item>
        <el-form-item label="后台令牌">
          <el-input v-model="form.token" type="password" show-password placeholder="输入 ADMIN_API_TOKEN" />
        </el-form-item>
        <el-button type="primary" size="large" :loading="loading" style="width: 100%" @click="handleLogin">
          登录后台
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const form = reactive({
  qq: undefined as number | undefined,
  token: '',
})

const handleLogin = async () => {
  if (!form.qq || !form.token.trim()) {
    ElMessage.warning('请完整填写 QQ 号和后台令牌')
    return
  }
  loading.value = true
  try {
    await authStore.login({ qq: form.qq, token: form.token.trim() })
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/overview'
    await router.replace(redirect)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.24), transparent 35%),
    radial-gradient(circle at bottom right, rgba(14, 165, 233, 0.2), transparent 40%),
    linear-gradient(180deg, #eff6ff 0%, #e2e8f0 100%);
}

.login-card {
  width: 420px;
  border-radius: 24px;
  padding: 12px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.12);
}

.login-title {
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
}

.login-subtitle {
  margin: 10px 0 24px;
  color: #64748b;
  font-size: 14px;
}
</style>
