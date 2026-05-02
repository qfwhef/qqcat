<template>
  <div class="login-shell">
    <div class="login-grid">
      <section class="brand-panel">
        <p class="brand-kicker">Xiaomiao Admin Console</p>
        <h1 class="brand-title">小喵机器人管理后台</h1>
        <p class="brand-subtitle">统一管理运行配置、消息追踪和服务状态。</p>
        <ul class="brand-points">
          <li>
            <el-icon><Monitor /></el-icon>
            <span>实时查看机器人运行状态</span>
          </li>
          <li>
            <el-icon><SetUp /></el-icon>
            <span>动态调整模型与工具策略</span>
          </li>
          <li>
            <el-icon><DataLine /></el-icon>
            <span>集中追踪会话与 AI 调用日志</span>
          </li>
        </ul>
      </section>

      <section class="form-panel">
        <div class="form-head">
          <h2>管理员登录</h2>
          <p>使用管理员 QQ 白名单和后台令牌继续。</p>
        </div>
        <el-form label-position="top" :model="form" @submit.prevent="handleLogin">
          <el-form-item label="QQ 号">
            <el-input
              v-model.number="form.qq"
              type="number"
              placeholder="输入管理员 QQ 号"
              :prefix-icon="User"
            />
          </el-form-item>
          <el-form-item label="后台令牌">
            <el-input
              v-model="form.token"
              type="password"
              show-password
              placeholder="输入 ADMIN_API_TOKEN"
              :prefix-icon="Key"
            />
          </el-form-item>
          <el-button
            class="login-btn"
            type="primary"
            size="large"
            :icon="Right"
            :loading="loading"
            @click="handleLogin"
          >
            登录后台
          </el-button>
        </el-form>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataLine, Key, Monitor, Right, SetUp, User } from '@element-plus/icons-vue'

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
  padding: clamp(18px, 3.2vw, 34px);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background:
    linear-gradient(140deg, rgba(40, 80, 155, 0.14), rgba(14, 116, 144, 0.14)),
    repeating-linear-gradient(
      125deg,
      rgba(148, 163, 184, 0.12) 0 18px,
      rgba(148, 163, 184, 0.02) 18px 38px
    ),
    linear-gradient(180deg, #f4f7fb 0%, #e9f0f5 100%);
  background-size: 100% 100%, 220% 220%, 100% 100%;
  animation: sceneDrift 26s ease-in-out infinite alternate;
}

.login-grid {
  position: relative;
  width: min(940px, 100%);
  min-height: min(560px, 100%);
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.34);
  box-shadow: 0 30px 75px rgba(15, 23, 42, 0.15);
  animation: panelLift 460ms ease-out both;
}

.login-grid::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  pointer-events: none;
  background: linear-gradient(
    110deg,
    rgba(255, 255, 255, 0.28),
    rgba(255, 255, 255, 0),
    rgba(255, 255, 255, 0.12)
  );
  mix-blend-mode: soft-light;
}

.brand-panel {
  padding: clamp(28px, 4vw, 46px);
  color: #e9f8ff;
  background:
    linear-gradient(160deg, #0e3a6a 0%, #0a6f87 54%, #0f8f8f 100%);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.brand-kicker {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(233, 248, 255, 0.78);
}

.brand-title {
  margin: 14px 0 12px;
  font-size: clamp(28px, 3.2vw, 38px);
  line-height: 1.12;
  letter-spacing: 0;
}

.brand-subtitle {
  margin: 0;
  max-width: 34ch;
  color: rgba(233, 248, 255, 0.84);
  line-height: 1.64;
  font-size: 15px;
}

.brand-points {
  margin: 28px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 12px;
}

.brand-points li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.2);
  font-size: 13px;
}

.brand-points .el-icon {
  font-size: 16px;
  color: #d5f6ff;
}

.form-panel {
  background: rgba(250, 252, 255, 0.96);
  padding: clamp(26px, 3.3vw, 38px);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.form-head h2 {
  margin: 0;
  color: #0f172a;
  font-size: 28px;
  line-height: 1.15;
  letter-spacing: 0;
}

.form-head p {
  margin: 10px 0 24px;
  color: #5a6a7d;
  font-size: 14px;
}

.login-btn {
  width: 100%;
  margin-top: 6px;
  border: none;
  background: linear-gradient(120deg, #1760c6 0%, #0f8f91 100%);
  box-shadow: 0 10px 24px rgba(16, 86, 164, 0.28);
  transition: transform 180ms ease, box-shadow 180ms ease, filter 180ms ease;
}

.login-btn:hover {
  transform: translateY(-1px);
  filter: brightness(1.03);
  box-shadow: 0 14px 28px rgba(16, 86, 164, 0.34);
}

.login-btn:active {
  transform: translateY(0);
}

:deep(.el-form-item) {
  margin-bottom: 18px;
}

:deep(.el-input__wrapper) {
  min-height: 42px;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.32) inset;
  transition: box-shadow 160ms ease;
}

:deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px rgba(15, 111, 166, 0.76) inset,
    0 0 0 3px rgba(15, 111, 166, 0.14);
}

@media (max-width: 940px) {
  .login-grid {
    grid-template-columns: 1fr;
  }

  .brand-panel {
    padding-bottom: 22px;
  }
}

@media (max-width: 560px) {
  .login-shell {
    padding: 12px;
  }

  .brand-panel {
    padding: 22px 18px 18px;
  }

  .brand-title {
    font-size: 27px;
  }

  .form-panel {
    padding: 20px 18px 22px;
  }
}

@keyframes panelLift {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.992);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes sceneDrift {
  from {
    background-position: center, 0% 0%, center;
  }
  to {
    background-position: center, 100% 100%, center;
  }
}
</style>
