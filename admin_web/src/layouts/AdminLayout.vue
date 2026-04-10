<template>
  <el-container class="layout-root">
    <el-aside :width="`${asideWidth}px`" class="aside-shell">
      <div class="brand-block">
        <div class="brand-title">小喵后台</div>
        <div class="brand-subtitle">运行配置与运维查询</div>
      </div>
      <el-menu
        :default-active="activeMenuIndex"
        :default-openeds="defaultOpeneds"
        router
        class="side-menu"
      >
        <template v-for="item in menus" :key="item.path">
          <el-sub-menu v-if="item.children?.length" :index="item.key">
            <template #title>{{ item.label }}</template>
            <template v-for="child in item.children" :key="child.path">
              <el-sub-menu v-if="child.children?.length" :index="child.key">
                <template #title>{{ child.label }}</template>
                <el-menu-item
                  v-for="grand in child.children"
                  :key="grand.path"
                  :index="grand.path"
                >
                  {{ grand.label }}
                </el-menu-item>
              </el-sub-menu>
              <el-menu-item v-else :index="child.path">
                {{ child.label }}
              </el-menu-item>
            </template>
          </el-sub-menu>
          <el-menu-item v-else :index="item.path">
            {{ item.label }}
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <div class="aside-resizer" @mousedown="startResize" />
    <el-container class="content-shell">
      <el-header class="header-shell">
        <div>
          <div class="header-title">管理后台</div>
          <div class="header-subtitle">配置热更新、消息检索、日志审计</div>
        </div>
        <div class="header-actions">
          <el-tag type="info">{{
            authStore.user?.nickname || "未登录"
          }}</el-tag>
          <el-button type="primary" plain @click="handleLogout"
            >退出登录</el-button
          >
        </div>
      </el-header>
      <el-main class="main-shell">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter, useRoute, RouterView } from "vue-router";
import { ElMessage } from "element-plus";

import { adminApi } from "../api/admin";
import { useAuthStore } from "../stores/auth";

interface MenuNode {
  key: string;
  label: string;
  path: string;
  children?: MenuNode[];
}

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();
const groupSessions = ref<any[]>([]);
const privateSessions = ref<any[]>([]);
const asideWidth = ref(200);
let removeResizeListeners: (() => void) | null = null;

const sessionMenuChildren = (type: "group" | "private") => {
  const sessions =
    type === "group" ? groupSessions.value : privateSessions.value;
  return sessions.map((item) => ({
    key: `${type}-${item.session_id}`,
    label: item.display_name,
    path: `/messages/${type}?session_id=${item.session_id}`,
  }));
};

const fallbackMenus: MenuNode[] = [
  { key: "overview", label: "概览", path: "/overview" },
  { key: "runtime", label: "AI 运行配置", path: "/runtime" },
  { key: "tools", label: "工具管理", path: "/tools" },
  { key: "prompts", label: "提示词", path: "/prompts" },
  { key: "access", label: "访问控制", path: "/access" },
  { key: "session-configs", label: "会话配置", path: "/session-configs" },
  { key: "messages", label: "消息查询", path: "/messages/group" },
  { key: "summaries", label: "摘要查询", path: "/summaries" },
  { key: "ai-calls", label: "AI 调用日志", path: "/ai-calls" },
];

const menus = computed<MenuNode[]>(() => {
  const source = authStore.menus.length
    ? authStore.menus.map((item) => ({
        ...item,
        path: item.path.replace("/admin-ui", ""),
      }))
    : fallbackMenus;
  return source.map((item) =>
    item.key === "messages"
      ? {
          key: "messages",
          label: item.label,
          path: "/messages/group",
          children: [
            {
              key: "messages-group",
              label: "群聊消息",
              path: "/messages/group",
              children: sessionMenuChildren("group"),
            },
            {
              key: "messages-private",
              label: "私聊消息",
              path: "/messages/private",
              children: sessionMenuChildren("private"),
            },
          ],
        }
      : ({ ...item } as MenuNode),
  );
});

const activeMenuIndex = computed(() => {
  const sessionId = route.query.session_id
    ? String(route.query.session_id)
    : "";
  if (route.path.startsWith("/messages/group") && sessionId) {
    return `/messages/group?session_id=${sessionId}`;
  }
  if (route.path.startsWith("/messages/private") && sessionId) {
    return `/messages/private?session_id=${sessionId}`;
  }
  return route.path;
});

const defaultOpeneds = computed(() => {
  const opened = ["messages"];
  if (route.path.startsWith("/messages/group")) {
    opened.push("messages-group");
  }
  if (route.path.startsWith("/messages/private")) {
    opened.push("messages-private");
  }
  return opened;
});

const loadMessageMenus = async () => {
  const [groupRes, privateRes] = await Promise.all([
    adminApi.getGroupMessageSessions(),
    adminApi.getPrivateMessageSessions(),
  ]);
  groupSessions.value = groupRes.items || [];
  privateSessions.value = privateRes.items || [];
};

const handleLogout = async () => {
  await authStore.logout();
  ElMessage.success("已退出后台登录");
  await router.replace("/login");
};

const startResize = (event: MouseEvent) => {
  event.preventDefault();
  const startX = event.clientX;
  const startWidth = asideWidth.value;
  const onMouseMove = (moveEvent: MouseEvent) => {
    const nextWidth = startWidth + (moveEvent.clientX - startX);
    asideWidth.value = Math.min(320, Math.max(168, nextWidth));
  };
  const onMouseUp = () => {
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
    removeResizeListeners = null;
  };
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onMouseUp);
  removeResizeListeners = () => {
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
  };
};

onMounted(loadMessageMenus);
onBeforeUnmount(() => {
  removeResizeListeners?.();
});
</script>

<style scoped>
.layout-root {
  height: 100vh;
  overflow: hidden;
}

.aside-shell {
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
  flex-shrink: 0;
  background: linear-gradient(180deg, #1f2a37 0%, #111827 100%);
  color: #f9fafb;
}

.aside-resizer {
  width: 6px;
  cursor: col-resize;
  background: linear-gradient(
    180deg,
    rgba(148, 163, 184, 0.08) 0%,
    rgba(148, 163, 184, 0.18) 100%
  );
}

.aside-resizer:hover {
  background: linear-gradient(
    180deg,
    rgba(59, 130, 246, 0.18) 0%,
    rgba(59, 130, 246, 0.3) 100%
  );
}

.brand-block {
  padding: 16px 14px 10px;
}

.brand-title {
  font-size: 19px;
  font-weight: 700;
}

.brand-subtitle {
  margin-top: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.72);
}

.side-menu {
  border-right: none;
  background: transparent;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: rgba(59, 130, 246, 0.12);
  --el-menu-text-color: rgba(255, 255, 255, 0.88);
  --el-menu-active-color: #ffffff;
  --el-menu-item-height: 28px;
}

.content-shell {
  height: 100vh;
  overflow: hidden;
}

.side-menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.88);
  height: var(--el-menu-item-height) !important;
  min-height: var(--el-menu-item-height) !important;
  line-height: var(--el-menu-item-height) !important;
  font-size: 12px;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}

.side-menu :deep(.el-sub-menu__title) {
  color: rgba(255, 255, 255, 0.88);
  height: var(--el-menu-item-height) !important;
  line-height: var(--el-menu-item-height) !important;
  font-size: 12px;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}

.side-menu :deep(.el-menu-item:hover),
.side-menu :deep(.el-sub-menu__title:hover) {
  background: rgba(59, 130, 246, 0.12) !important;
  color: #ffffff;
}

.side-menu :deep(.el-menu),
.side-menu :deep(.el-sub-menu .el-menu) {
  background: transparent !important;
}

.side-menu :deep(.el-menu-item.is-active) {
  background: rgba(59, 130, 246, 0.2);
  color: #ffffff;
}

.side-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: #ffffff;
  background: rgba(59, 130, 246, 0.12);
}

.side-menu :deep(.el-sub-menu.is-opened > .el-sub-menu__title) {
  background: rgba(59, 130, 246, 0.1);
}

.side-menu :deep(.el-sub-menu .el-menu-item) {
  height: var(--el-menu-item-height) !important;
  min-height: var(--el-menu-item-height) !important;
  line-height: var(--el-menu-item-height) !important;
  padding-left: 32px !important;
  background: transparent !important;
}

.side-menu :deep(.el-sub-menu .el-sub-menu .el-menu-item) {
  padding-left: 44px !important;
}

.side-menu :deep(.el-sub-menu .el-menu-item.is-active) {
  background: rgba(59, 130, 246, 0.18) !important;
}

.header-shell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.header-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.header-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: #64748b;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.main-shell {
  overflow-y: auto;
  padding: 14px 16px 4px !important;
  display: flex;
  flex-direction: column;
}
</style>
