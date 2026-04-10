<template>
  <div class="messages-page-root">
    <el-card class="page-card">
      <div ref="messagesContentRef" class="messages-content">
        <div ref="toolbarRef" class="table-toolbar">
          <div>
            <div style="font-size: 16px; font-weight: 700; color: #111827">
              {{ activeTab === "group" ? "群聊消息" : "私聊消息" }}
            </div>
            <div style="margin-top: 4px; color: #64748b; font-size: 13px">
              当前会话：
              <span v-if="selectedSession"
                >{{ selectedSession.display_name }}（{{
                  selectedSession.session_id
                }}）</span
              >
              <span v-else>未选择，请先从主菜单选择具体会话</span>
            </div>
          </div>
          <div style="display: flex; gap: 10px">
            <el-button @click="clearSelectedSession">返回会话类型</el-button>
            <el-button
              type="danger"
              :disabled="!selectedRows.length"
              @click="handleBatchDelete"
            >
              批量删除（{{ selectedRows.length }}）
            </el-button>
          </div>
        </div>

        <el-form
          ref="filterFormRef"
          class="toolbar-form compact-filter-form"
          :inline="true"
        >
          <!-- <el-form-item label="发送者 QQ">
              <el-input v-model.number="filters.sender_user_id" placeholder="发送者QQ" style="width: 150px" clearable />
            </el-form-item> -->
          <el-form-item label="角色">
            <el-select v-model="filters.role" clearable style="width: 120px">
              <el-option label="user" value="user" />
              <el-option label="assistant" value="assistant" />
              <el-option label="tool" value="tool" />
              <el-option label="system" value="system" />
            </el-select>
          </el-form-item>
          <el-form-item label="关键词">
            <el-input
              v-model="filters.keyword"
              placeholder="内容/引用/工具名"
              style="width: 200px"
              clearable
            />
          </el-form-item>
          <el-form-item label="时间范围">
            <el-select
              v-model="timePreset"
              style="width: 160px"
              @change="applyTimePreset"
            >
              <el-option label="全部" value="all" />
              <el-option label="24小时内" value="last_24h" />
              <el-option label="7天内" value="last_7d" />
              <el-option label="30天内" value="last_30d" />
              <el-option label="7天外" value="older_7d" />
              <el-option label="30天外" value="older_30d" />
              <el-option label="自定义" value="custom" />
            </el-select>
          </el-form-item>
          <el-form-item label="是否引用">
            <el-select
              v-model="filters.is_reply"
              clearable
              style="width: 120px"
            >
              <el-option label="是" :value="true" />
              <el-option label="否" :value="false" />
            </el-select>
          </el-form-item>
          <el-form-item label="工具消息">
            <el-select v-model="filters.is_tool" clearable style="width: 120px">
              <el-option label="是" :value="true" />
              <el-option label="否" :value="false" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="timePreset === 'custom'" label="开始时间">
            <el-input
              v-model="filters.start_at"
              placeholder="YYYY-MM-DD HH:mm:ss"
              style="width: 180px"
              clearable
            />
          </el-form-item>
          <el-form-item v-if="timePreset === 'custom'" label="结束时间">
            <el-input
              v-model="filters.end_at"
              placeholder="YYYY-MM-DD HH:mm:ss"
              style="width: 180px"
              clearable
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" @click="handleSearch"
              >查询</el-button
            >
          </el-form-item>
        </el-form>

        <div class="table-scroll-shell">
          <el-table
            :data="rows.items"
            :max-height="tableMaxHeight"
            @row-click="openDetail"
            @selection-change="handleSelectionChange"
          >
            <el-table-column type="selection" width="48" />
            <el-table-column label="发送者昵称" min-width="160">
              <template #default="{ row }">{{
                displaySenderName(row)
              }}</template>
            </el-table-column>
            <el-table-column label="内容" min-width="360">
              <template #default="{ row }">{{
                summarize(row.content_text)
              }}</template>
            </el-table-column>
            <el-table-column prop="role" label="角色" width="100" />
            <el-table-column
              prop="sender_user_id"
              label="QQ号"
              min-width="130"
            />
            <el-table-column prop="message_type" label="类型" width="100" />
            <el-table-column prop="tool_name" label="工具" min-width="120" />
            <el-table-column prop="model_name" label="模型" min-width="160" />
            <el-table-column prop="created_at" label="时间" min-width="170" />
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <div style="display: flex; gap: 8px">
                  <el-button link type="primary" @click.stop="openEdit(row)"
                    >编辑</el-button
                  >
                  <el-button
                    link
                    type="danger"
                    @click.stop="handleDeleteRow(row)"
                    >删除</el-button
                  >
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div ref="paginationBarRef" class="pagination-bar">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next"
            :total="rows.total"
            :page-size="rows.page_size"
            :current-page="rows.page"
            :page-sizes="[10, 20, 50, 100, 200]"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </div>
    </el-card>

    <el-drawer v-model="detailVisible" title="消息详情" size="55%">
      <el-descriptions v-if="currentRow" :column="2" border>
        <el-descriptions-item label="消息ID">{{
          currentRow.id
        }}</el-descriptions-item>
        <el-descriptions-item label="平台消息ID">{{
          currentRow.platform_message_id || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="会话ID">{{
          activeTab === "group" ? currentRow.group_id : currentRow.peer_user_id
        }}</el-descriptions-item>
        <el-descriptions-item label="发送者">{{
          currentRow.sender_user_id || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="角色">{{
          currentRow.role
        }}</el-descriptions-item>
        <el-descriptions-item label="消息类型">{{
          currentRow.message_type
        }}</el-descriptions-item>
        <el-descriptions-item label="工具">{{
          currentRow.tool_name || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{
          currentRow.model_name || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="引用消息">{{
          currentRow.is_reply ? "是" : "否"
        }}</el-descriptions-item>
        <el-descriptions-item label="被引平台ID">{{
          currentRow.quoted_platform_message_id || "-"
        }}</el-descriptions-item>
      </el-descriptions>
      <el-divider content-position="left">标准化文本</el-divider>
      <pre class="json-block">{{ currentRow?.content_text || "" }}</pre>
      <el-divider content-position="left">引用文本</el-divider>
      <pre class="json-block">{{ currentRow?.quoted_text || "-" }}</pre>
      <el-divider content-position="left">原始消息 JSON</el-divider>
      <pre class="json-block">{{
        formatJson(currentRow?.raw_message_json)
      }}</pre>
      <el-divider content-position="left">工具参数</el-divider>
      <pre class="json-block">{{ formatJson(currentRow?.tool_args_json) }}</pre>
    </el-drawer>

    <el-dialog v-model="editVisible" title="编辑消息" width="720px">
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="发送者昵称">
          <el-input v-model="editForm.sender_nickname" />
        </el-form-item>
        <el-form-item label="QQ号">
          <el-input v-model.number="editForm.sender_user_id" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="editForm.role" style="width: 180px">
            <el-option label="user" value="user" />
            <el-option label="assistant" value="assistant" />
            <el-option label="tool" value="tool" />
            <el-option label="system" value="system" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="editForm.message_type" style="width: 180px">
            <el-option label="text" value="text" />
            <el-option label="image" value="image" />
            <el-option label="mixed" value="mixed" />
            <el-option label="tool" value="tool" />
          </el-select>
        </el-form-item>
        <el-form-item label="工具">
          <el-input v-model="editForm.tool_name" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="editForm.model_name" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="editForm.content_text" type="textarea" :rows="6" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { adminApi } from "../api/admin";

const route = useRoute();
const router = useRouter();
const activeTab = ref<"group" | "private">("group");
const loading = ref(false);
const saving = ref(false);
const detailVisible = ref(false);
const editVisible = ref(false);
const currentRow = ref<any>(null);
const editingRow = ref<any>(null);
const timePreset = ref<
  | "all"
  | "last_24h"
  | "last_7d"
  | "last_30d"
  | "older_7d"
  | "older_30d"
  | "custom"
>("all");
const selectedSession = ref<any>(null);
const selectedRows = ref<any[]>([]);
const messagesContentRef = ref<HTMLElement | null>(null);
const toolbarRef = ref<HTMLElement | null>(null);
const filterFormRef = ref<any>(null);
const paginationBarRef = ref<HTMLElement | null>(null);
const tableMaxHeightPx = ref(360);
let resizeObserver: ResizeObserver | null = null;
const rows = reactive({ items: [] as any[], page: 1, page_size: 20, total: 0 });
const groupSessions = ref<any[]>([]);
const privateSessions = ref<any[]>([]);
const filters = reactive({
  session_id: undefined as number | undefined,
  sender_user_id: undefined as number | undefined,
  role: "",
  keyword: "",
  start_at: "",
  end_at: "",
  is_reply: undefined as boolean | undefined,
  is_tool: undefined as boolean | undefined,
});
const editForm = reactive({
  sender_user_id: undefined as number | undefined,
  sender_nickname: "",
  role: "user",
  message_type: "text",
  content_text: "",
  tool_name: "",
  model_name: "",
});

const summarize = (value: string) =>
  value?.length > 80 ? `${value.slice(0, 80)}...` : value;
const displaySenderName = (row: any) =>
  row.sender_card || row.sender_nickname || "-";
const tableMaxHeight = computed(() => Math.max(220, tableMaxHeightPx.value));

const formatJson = (value: unknown) => {
  if (!value) return "-";
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
};

const formatDateTime = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

const getElementHeight = (target: any) => {
  const el = target?.$el ?? target;
  return el instanceof HTMLElement ? el.offsetHeight : 0;
};

const recalcTableHeight = async () => {
  await nextTick();
  const container = messagesContentRef.value;
  if (!container) return;
  const top = container.getBoundingClientRect().top;
  const viewport = window.innerHeight;
  const toolbarHeight = getElementHeight(toolbarRef.value);
  const formHeight = getElementHeight(filterFormRef.value);
  const paginationHeight = getElementHeight(paginationBarRef.value);
  const available = viewport - top - 24;
  tableMaxHeightPx.value =
    available - toolbarHeight - formHeight - paginationHeight - 18;
};

const applyTimePreset = async () => {
  const now = new Date();
  if (timePreset.value === "all") {
    filters.start_at = "";
    filters.end_at = "";
  } else if (timePreset.value === "last_24h") {
    filters.start_at = formatDateTime(
      new Date(now.getTime() - 24 * 60 * 60 * 1000),
    );
    filters.end_at = "";
  } else if (timePreset.value === "last_7d") {
    filters.start_at = formatDateTime(
      new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000),
    );
    filters.end_at = "";
  } else if (timePreset.value === "last_30d") {
    filters.start_at = formatDateTime(
      new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000),
    );
    filters.end_at = "";
  } else if (timePreset.value === "older_7d") {
    filters.start_at = "";
    filters.end_at = formatDateTime(
      new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000),
    );
  } else if (timePreset.value === "older_30d") {
    filters.start_at = "";
    filters.end_at = formatDateTime(
      new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000),
    );
  }
  rows.page = 1;
  await loadMessages();
};

const loadMessages = async () => {
  if (!filters.session_id) {
    Object.assign(rows, { items: [], total: 0 });
    return;
  }
  loading.value = true;
  try {
    const params = { page: rows.page, page_size: rows.page_size, ...filters };
    const data =
      activeTab.value === "group"
        ? await adminApi.getGroupMessages(params)
        : await adminApi.getPrivateMessages(params);
    Object.assign(rows, data);
    selectedRows.value = [];
  } finally {
    loading.value = false;
  }
};

const loadSessionMenus = async () => {
  const [groupRes, privateRes] = await Promise.all([
    adminApi.getGroupMessageSessions(),
    adminApi.getPrivateMessageSessions(),
  ]);
  groupSessions.value = groupRes.items || [];
  privateSessions.value = privateRes.items || [];
};

const handleSearch = async () => {
  rows.page = 1;
  await loadMessages();
};

const handlePageChange = async (page: number) => {
  rows.page = page;
  await loadMessages();
};

const handlePageSizeChange = async (pageSize: number) => {
  rows.page_size = pageSize;
  rows.page = 1;
  await loadMessages();
  await recalcTableHeight();
};

const handleSelectionChange = (selection: any[]) => {
  selectedRows.value = selection;
};

const clearSelectedSession = async () => {
  selectedSession.value = null;
  filters.session_id = undefined;
  selectedRows.value = [];
  rows.page = 1;
  await router.push(
    activeTab.value === "group" ? "/messages/group" : "/messages/private",
  );
};

const openDetail = async (row: any) => {
  currentRow.value =
    activeTab.value === "group"
      ? await adminApi.getGroupMessageDetail(Number(filters.session_id), row.id)
      : await adminApi.getPrivateMessageDetail(
          Number(filters.session_id),
          row.id,
        );
  detailVisible.value = true;
};

const openEdit = async (row: any) => {
  const detail =
    activeTab.value === "group"
      ? await adminApi.getGroupMessageDetail(Number(filters.session_id), row.id)
      : await adminApi.getPrivateMessageDetail(
          Number(filters.session_id),
          row.id,
        );
  editingRow.value = detail;
  editForm.sender_user_id = detail.sender_user_id;
  editForm.sender_nickname = detail.sender_card || detail.sender_nickname || "";
  editForm.role = detail.role || "user";
  editForm.message_type = detail.message_type || "text";
  editForm.content_text = detail.content_text || "";
  editForm.tool_name = detail.tool_name || "";
  editForm.model_name = detail.model_name || "";
  editVisible.value = true;
};

const saveEdit = async () => {
  if (!editingRow.value || !filters.session_id) return;
  saving.value = true;
  try {
    const payload: Record<string, unknown> = {
      sender_user_id: editForm.sender_user_id,
      sender_nickname: editForm.sender_nickname,
      role: editForm.role,
      message_type: editForm.message_type,
      content_text: editForm.content_text,
      tool_name: editForm.tool_name,
      model_name: editForm.model_name,
    };
    if (activeTab.value === "group") {
      payload.sender_card = editForm.sender_nickname;
      await adminApi.updateGroupMessage(
        Number(filters.session_id),
        editingRow.value.id,
        payload,
      );
    } else {
      await adminApi.updatePrivateMessage(
        Number(filters.session_id),
        editingRow.value.id,
        payload,
      );
    }
    ElMessage.success("消息已更新");
    editVisible.value = false;
    await loadMessages();
  } finally {
    saving.value = false;
  }
};

const performDelete = async (messageIds: number[]) => {
  if (!filters.session_id || messageIds.length === 0) return;
  if (activeTab.value === "group") {
    await adminApi.deleteGroupMessages(Number(filters.session_id), messageIds);
  } else {
    await adminApi.deletePrivateMessages(
      Number(filters.session_id),
      messageIds,
    );
  }
  ElMessage.success(`已删除 ${messageIds.length} 条消息`);
  await loadSessionMenus();
  await loadMessages();
};

const handleDeleteRow = async (row: any) => {
  await ElMessageBox.confirm(`确认删除消息 #${row.id} 吗？`, "删除消息", {
    type: "warning",
  });
  await performDelete([row.id]);
};

const handleBatchDelete = async () => {
  if (!selectedRows.value.length) return;
  await ElMessageBox.confirm(
    `确认批量删除 ${selectedRows.value.length} 条消息吗？`,
    "批量删除",
    {
      type: "warning",
    },
  );
  await performDelete(selectedRows.value.map((item) => Number(item.id)));
};

const applyRouteTab = async () => {
  const nextTab: "group" | "private" = route.path.includes("/messages/private")
    ? "private"
    : "group";
  const tabChanged = activeTab.value !== nextTab;
  activeTab.value = nextTab;
  const sessionId = route.query.session_id
    ? Number(route.query.session_id)
    : undefined;
  filters.session_id = Number.isFinite(sessionId as number)
    ? sessionId
    : undefined;
  const sessions =
    activeTab.value === "group" ? groupSessions.value : privateSessions.value;
  selectedSession.value =
    sessions.find((item) => Number(item.session_id) === filters.session_id) ||
    null;
  if (tabChanged && !filters.session_id) {
    selectedRows.value = [];
  }
  rows.page = 1;
  await loadMessages();
  await recalcTableHeight();
};

const syncViewportHeight = async () => {
  await recalcTableHeight();
};

watch(
  () => route.fullPath,
  async () => {
    await applyRouteTab();
  },
);

onMounted(async () => {
  window.addEventListener("resize", syncViewportHeight);
  resizeObserver = new ResizeObserver(() => {
    void recalcTableHeight();
  });
  if (messagesContentRef.value)
    resizeObserver.observe(messagesContentRef.value);
  if (toolbarRef.value) resizeObserver.observe(toolbarRef.value);
  const filterEl = filterFormRef.value?.$el;
  if (filterEl instanceof HTMLElement) resizeObserver.observe(filterEl);
  if (paginationBarRef.value) resizeObserver.observe(paginationBarRef.value);
  await loadSessionMenus();
  await applyRouteTab();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", syncViewportHeight);
  resizeObserver?.disconnect();
});
</script>

<style scoped>
.messages-layout {
  display: block;
}

.messages-page-root {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.messages-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding-bottom: 14px;
}

.table-scroll-shell {
  overflow: hidden;
  margin-top: 8px;
}

.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-height: 32px;
  margin-top: 6px;
  margin-bottom: 0;
  padding-bottom: 0;
  background: #fff;
}

.compact-filter-form {
  margin: 8px 0;
}

:deep(.page-card > .el-card__body) {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding-bottom: 2px !important;
  overflow: hidden;
}

:deep(.messages-page-root > .page-card) {
  flex: 1;
  min-height: 0;
}
</style>
