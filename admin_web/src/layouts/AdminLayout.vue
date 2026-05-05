<template>
  <el-container class="layout-root">
    <el-aside :width="`${asideWidth}px`" class="aside-shell">
      <div class="brand-block">
        <div class="brand-top">
          <div class="brand-mark">
            <el-icon><Avatar /></el-icon>
          </div>
          <div>
            <div class="brand-title">小喵后台</div>
            <div class="brand-subtitle">运行配置与运维查询</div>
          </div>
        </div>
        <div class="brand-meta">
          <span class="meta-chip">在线管理</span>
          <span class="meta-chip is-muted">受控访问</span>
        </div>
      </div>
      <div class="menu-wrap">
        <el-menu
          :default-active="activeMenuIndex"
          :default-openeds="defaultOpeneds"
          router
          class="side-menu"
        >
          <template v-for="item in menus" :key="item.path">
            <el-sub-menu v-if="item.children?.length" :index="item.key">
              <template #title>
                <el-icon class="menu-icon"><component :is="menuIcon(item.key)" /></el-icon>
                <span>{{ item.label }}</span>
              </template>
              <template v-for="child in item.children" :key="child.path">
                <el-sub-menu v-if="child.children?.length" :index="child.key">
                  <template #title>
                    <el-icon class="menu-icon"><component :is="menuIcon(child.key)" /></el-icon>
                    <span>{{ child.label }}</span>
                  </template>
                  <el-menu-item
                    v-for="grand in child.children"
                    :key="grand.path"
                    :index="grand.path"
                  >
                    <el-icon class="menu-icon"><component :is="menuIcon(grand.key)" /></el-icon>
                    {{ grand.label }}
                  </el-menu-item>
                </el-sub-menu>
                <el-menu-item v-else :index="child.path">
                  <el-icon class="menu-icon"><component :is="menuIcon(child.key)" /></el-icon>
                  {{ child.label }}
                </el-menu-item>
              </template>
            </el-sub-menu>
            <el-menu-item v-else :index="item.path">
              <el-icon class="menu-icon"><component :is="menuIcon(item.key)" /></el-icon>
              {{ item.label }}
            </el-menu-item>
          </template>
        </el-menu>
      </div>
      <div class="aside-footer">
        <div class="footer-avatar">
          <el-icon><UserFilled /></el-icon>
        </div>
        <div class="footer-meta">
          <div class="footer-label">当前账号</div>
          <div class="footer-user">{{ authStore.user?.nickname || "未登录" }}</div>
        </div>
      </div>
    </el-aside>
    <div class="aside-resizer" @mousedown="startResize" />
    <el-container class="content-shell">
      <el-header class="header-shell">
        <div>
          <div class="header-title">管理后台</div>
          <div class="header-subtitle">配置热更新、消息检索、日志审计</div>
        </div>
        <div class="header-actions">
          <el-button class="notify-btn" text>
            <el-icon><Bell /></el-icon>
          </el-button>
          <el-tooltip content="切换主题色" placement="bottom">
            <el-button class="theme-btn" text @click="toggleTheme">
              <el-icon><Brush /></el-icon>
            </el-button>
          </el-tooltip>
          <div class="header-user-pill">
            <span>{{ authStore.user?.nickname || "未登录" }}</span>
            <el-icon><ArrowDown /></el-icon>
          </div>
          <el-button class="logout-btn" plain @click="handleLogout">退出登录</el-button>
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
import {
  ArrowDown,
  Avatar,
  Bell,
  Brush,
  DataAnalysis,
  Monitor,
  Lock,
  MessageBox,
  Operation,
  Reading,
  SetUp,
  Timer,
  Tools,
  UserFilled,
  Document,
  ChatLineRound,
  List,
} from "@element-plus/icons-vue";

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
const themeMode = ref<"blue" | "pink">("blue");
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
  { key: "health", label: "系统检测", path: "/health" },
  { key: "scheduled-tasks", label: "定时任务", path: "/scheduled-tasks" },
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
              key: "messages-session-manager",
              label: "会话管理",
              path: "/messages/session-manager",
            },
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
  const opened: string[] = [];
  if (!route.path.startsWith("/messages")) {
    return opened;
  }
  opened.push("messages");
  if (route.path.startsWith("/messages/group")) {
    opened.push("messages-group");
  }
  if (route.path.startsWith("/messages/private")) {
    opened.push("messages-private");
  }
  return opened;
});

const menuIcon = (key: string) => {
  const normalized = String(key || "");
  if (normalized === "overview") return DataAnalysis;
  if (normalized === "health") return Monitor;
  if (normalized === "runtime") return SetUp;
  if (normalized === "tools") return Tools;
  if (normalized === "scheduled-tasks") return Timer;
  if (normalized === "access") return Lock;
  if (normalized === "session-configs") return Operation;
  if (normalized === "messages") return MessageBox;
  if (normalized === "messages-session-manager") return List;
  if (normalized.startsWith("messages-group")) return ChatLineRound;
  if (normalized.startsWith("messages-private")) return ChatLineRound;
  if (normalized.startsWith("group-")) return Document;
  if (normalized.startsWith("private-")) return Document;
  if (normalized === "summaries") return Reading;
  if (normalized === "ai-calls") return DataAnalysis;
  return Document;
};

const loadMessageMenus = async () => {
  const [groupRes, privateRes] = await Promise.all([
    adminApi.getGroupMessageSessions(),
    adminApi.getPrivateMessageSessions(),
  ]);
  groupSessions.value = groupRes.items || [];
  privateSessions.value = privateRes.items || [];
};

const handleMessageSessionsUpdated = () => {
  void loadMessageMenus();
};

const handleLogout = async () => {
  await authStore.logout();
  ElMessage.success("已退出后台登录");
  await router.replace("/login");
};

const applyTheme = (mode: "blue" | "pink") => {
  themeMode.value = mode;
  document.documentElement.setAttribute("data-theme", mode);
  localStorage.setItem("admin-theme-mode", mode);
};

const toggleTheme = () => {
  applyTheme(themeMode.value === "blue" ? "pink" : "blue");
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

onMounted(() => {
  const current = document.documentElement.getAttribute("data-theme");
  if (current === "pink" || current === "blue") {
    themeMode.value = current;
  } else {
    applyTheme("blue");
  }
  window.addEventListener("message-sessions-updated", handleMessageSessionsUpdated);
  void loadMessageMenus();
});
onBeforeUnmount(() => {
  window.removeEventListener("message-sessions-updated", handleMessageSessionsUpdated);
  removeResizeListeners?.();
});
</script>

<style scoped>
.layout-root {
  height: 100vh;
  overflow: hidden;
  background: #edf2f8;
}

.aside-shell {
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #f7f9fc;
  color: #0f172a;
  border-right: 1px solid rgba(148, 163, 184, 0.2);
}

.aside-resizer {
  width: 4px;
  cursor: col-resize;
  background: rgba(148, 163, 184, 0.16);
  transition: background 160ms ease;
}

.aside-resizer:hover {
  background: rgba(var(--theme-primary-rgb), 0.4);
}

.brand-block {
  padding: 16px 14px 10px;
}

.brand-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-mark {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-size: 19px;
  background: linear-gradient(145deg, var(--theme-gradient-start) 0%, var(--theme-gradient-end) 100%);
  color: #ffffff;
  box-shadow: 0 8px 20px rgba(var(--theme-primary-rgb), 0.3);
}

.brand-title {
  font-size: 30px;
  line-height: 1.12;
  color: #111827;
  font-weight: 700;
}

.brand-subtitle {
  margin-top: 3px;
  font-size: 11px;
  color: #64748b;
}

.brand-meta {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.meta-chip {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  color: var(--theme-primary-ink);
  background: rgba(var(--theme-primary-rgb), 0.12);
  border: 1px solid rgba(var(--theme-primary-rgb), 0.24);
}

.meta-chip.is-muted {
  color: #0f766e;
  background: rgba(20, 184, 166, 0.1);
  border: 1px solid rgba(20, 184, 166, 0.22);
}

.menu-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 6px 10px 10px;
}

.side-menu {
  border-right: none;
  background: transparent;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: rgba(var(--theme-primary-rgb), 0.12);
  --el-menu-text-color: #334155;
  --el-menu-active-color: var(--theme-primary-strong);
  --el-menu-item-height: 40px;
}

.content-shell {
  height: 100vh;
  overflow: hidden;
}

.side-menu :deep(.el-menu-item) {
  position: relative;
  color: #334155;
  height: var(--el-menu-item-height) !important;
  min-height: var(--el-menu-item-height) !important;
  line-height: var(--el-menu-item-height) !important;
  font-size: 12px;
  border-radius: 10px;
  margin: 2px 6px;
  padding-left: 12px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  transition: background 140ms ease, color 140ms ease;
}

.side-menu :deep(.el-sub-menu__title) {
  position: relative;
  color: #334155;
  height: var(--el-menu-item-height) !important;
  line-height: var(--el-menu-item-height) !important;
  font-size: 12px;
  border-radius: 10px;
  margin: 2px 6px;
  padding-left: 12px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  transition: background 140ms ease, color 140ms ease;
}

.side-menu :deep(.el-menu-item:hover),
.side-menu :deep(.el-sub-menu__title:hover) {
  background: rgba(var(--theme-primary-rgb), 0.1) !important;
  color: var(--theme-primary-ink);
}

.side-menu :deep(.el-menu),
.side-menu :deep(.el-sub-menu .el-menu) {
  background: transparent !important;
}

.side-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(var(--theme-primary-rgb), 0.14), rgba(var(--theme-primary-rgb), 0.08)) !important;
  color: var(--theme-primary-ink);
  box-shadow: inset 0 0 0 1px rgba(var(--theme-primary-rgb), 0.22);
}

.side-menu :deep(.el-menu-item.is-active)::before {
  content: "";
  position: absolute;
  left: -2px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 3px;
  background: linear-gradient(180deg, var(--theme-primary), var(--theme-primary-strong));
}

.side-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: #334155;
  background: transparent;
}

.side-menu :deep(.el-sub-menu > .el-menu > .el-menu-item) {
  height: var(--el-menu-item-height) !important;
  min-height: var(--el-menu-item-height) !important;
  line-height: var(--el-menu-item-height) !important;
  padding-left: 12px !important;
  background: transparent !important;
}

.side-menu :deep(.el-sub-menu > .el-menu > .el-sub-menu .el-menu-item) {
  padding-left: 34px !important;
}

.side-menu :deep(.el-sub-menu .el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(var(--theme-primary-rgb), 0.13), rgba(var(--theme-primary-rgb), 0.06)) !important;
}

.aside-footer {
  margin: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(var(--theme-primary-rgb), 0.1), rgba(var(--theme-primary-rgb), 0.05));
  border: 1px solid rgba(var(--theme-primary-rgb), 0.2);
  display: flex;
  align-items: center;
  gap: 10px;
}

.footer-avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: var(--theme-primary-strong);
  background: rgba(var(--theme-primary-rgb), 0.14);
}

.footer-meta {
  min-width: 0;
}

.footer-label {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.footer-user {
  margin-top: 5px;
  font-size: 12px;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-shell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px 12px;
  background: #ffffff;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  flex-shrink: 0;
}

.header-title {
  font-size: 32px;
  line-height: 1.12;
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
  gap: 10px;
}

.notify-btn {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: #ffffff;
}

.theme-btn {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  border: 1px solid rgba(var(--theme-primary-rgb), 0.26);
  background: rgba(var(--theme-primary-rgb), 0.08);
  color: var(--theme-primary-strong);
}

.header-user-pill {
  height: 34px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: #f8fafc;
  color: #334155;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
}

.logout-btn {
  height: 34px;
  border-color: rgba(239, 68, 68, 0.35);
  color: #ef4444;
}

.menu-icon {
  margin-right: 8px;
  font-size: 15px;
  color: #94a3b8;
}

.side-menu :deep(.el-sub-menu > .el-sub-menu__title) .menu-icon {
  color: #94a3b8;
}

.side-menu :deep(.el-sub-menu .el-menu-item.is-active) .menu-icon,
.side-menu :deep(.el-menu-item.is-active) .menu-icon {
  color: var(--theme-primary);
}

.main-shell {
  overflow-y: auto;
  padding: 16px 20px 10px !important;
  display: flex;
  flex-direction: column;
  background: #edf2f8;
}
</style>
