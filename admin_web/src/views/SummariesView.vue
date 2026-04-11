<template>
  <div>
    <el-card class="page-card">
      <div ref="summariesContentRef" class="summaries-content">
        <div class="table-toolbar" style="margin-bottom: 8px">
          <div style="font-size: 16px; font-weight: 700; color: #111827">摘要查询</div>
          <div style="display: flex; gap: 10px">
            <el-button :loading="loading" @click="loadData">刷新</el-button>
            <el-button type="primary" @click="openCreateDialog">新增摘要</el-button>
          </div>
        </div>
        <el-tabs ref="tabsRef" v-model="activeTab" @tab-change="handleTabChange">
          <el-tab-pane label="群聊摘要" name="group" />
          <el-tab-pane label="私聊摘要" name="private" />
        </el-tabs>
        <el-form ref="filterFormRef" :inline="true" class="toolbar-form compact-filter-form">
          <el-form-item label="会话 ID">
            <el-input v-model.number="filters.session_id" placeholder="群号/用户QQ" style="width: 180px" clearable />
          </el-form-item>
          <el-form-item label="是否活跃">
            <el-select v-model="filters.is_active" clearable style="width: 120px">
              <el-option label="是" :value="true" />
              <el-option label="否" :value="false" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" @click="handleSearch">查询</el-button>
          </el-form-item>
        </el-form>
        <div class="table-scroll-shell">
          <el-table :data="rows.items" :max-height="tableMaxHeight">
            <el-table-column label="群名 / QQ昵称" min-width="180">
              <template #default="{ row }">
                {{ displaySessionName(row) }}
              </template>
            </el-table-column>
            <el-table-column prop="session_id" label="群号 / QQ号" min-width="140" />
            <el-table-column prop="summary_version" label="摘要版本" width="100" />
            <el-table-column label="摘要内容" min-width="320">
              <template #default="{ row }">{{ summarize(row.summary_text) }}</template>
            </el-table-column>
            <el-table-column label="活跃" width="90">
              <template #default="{ row }">{{ row.is_active ? "是" : "否" }}</template>
            </el-table-column>
            <el-table-column prop="created_by_model" label="模型" min-width="160" />
            <el-table-column prop="source_start_message_id" label="起始消息ID" min-width="120" />
            <el-table-column prop="source_end_message_id" label="结束消息ID" min-width="120" />
            <el-table-column prop="created_at" label="创建时间" min-width="160" />
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="{ row }">
                <div style="display: flex; gap: 8px">
                  <el-button link type="info" @click="openDetail(row)">查看</el-button>
                  <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
                  <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div ref="paginationBarRef" class="summary-pagination-bar">
          <el-pagination
            background
            layout="total, prev, pager, next"
            :total="rows.total"
            :page-size="rows.page_size"
            :current-page="rows.page"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </el-card>

    <el-drawer v-model="detailVisible" title="摘要详情" size="50%">
      <el-descriptions v-if="currentRow" :column="2" border>
        <el-descriptions-item label="群名 / QQ昵称">
          {{ displaySessionName(currentRow) }}
        </el-descriptions-item>
        <el-descriptions-item label="会话ID">{{ currentRow.session_id }}</el-descriptions-item>
        <el-descriptions-item label="摘要版本">{{ currentRow.summary_version }}</el-descriptions-item>
        <el-descriptions-item label="起始消息">{{ currentRow.source_start_message_id || "-" }}</el-descriptions-item>
        <el-descriptions-item label="结束消息">{{ currentRow.source_end_message_id || "-" }}</el-descriptions-item>
        <el-descriptions-item label="覆盖消息数">{{ currentRow.source_message_count }}</el-descriptions-item>
        <el-descriptions-item label="当前摘要版本">{{ currentRow.current_summary_version || "-" }}</el-descriptions-item>
        <el-descriptions-item label="最后消息ID">{{ currentRow.last_message_id || "-" }}</el-descriptions-item>
        <el-descriptions-item label="最后摘要消息ID">{{ currentRow.last_summary_message_id || "-" }}</el-descriptions-item>
        <el-descriptions-item label="摘要冷却截止">{{ currentRow.summary_cooldown_until || "-" }}</el-descriptions-item>
      </el-descriptions>
      <el-divider content-position="left">摘要文本</el-divider>
      <pre class="json-block">{{ currentRow?.summary_text || "" }}</pre>
      <el-divider content-position="left">结构化摘要</el-divider>
      <pre class="json-block">{{ formatJson(currentRow?.summary_json) }}</pre>
    </el-drawer>

    <el-dialog v-model="dialogVisible" :title="dialogMode === 'create' ? '新增摘要' : '编辑摘要'" width="760px">
      <el-form :model="form" label-position="top">
        <div class="split-grid">
          <div>
            <el-form-item label="会话 ID">
              <el-input v-model.number="form.session_id" :disabled="dialogMode === 'edit'" />
            </el-form-item>
            <el-form-item label="群名 / QQ昵称">
              <el-input v-model="form.session_name" />
            </el-form-item>
            <el-form-item label="模型">
              <el-input v-model="form.created_by_model" />
            </el-form-item>
            <el-form-item label="是否活跃">
              <el-switch v-model="form.is_active" />
            </el-form-item>
          </div>
          <div>
            <el-form-item label="起始消息ID">
              <el-input v-model.number="form.source_start_message_id" />
            </el-form-item>
            <el-form-item label="结束消息ID">
              <el-input v-model.number="form.source_end_message_id" />
            </el-form-item>
            <el-form-item label="覆盖消息数">
              <el-input v-model.number="form.source_message_count" />
            </el-form-item>
          </div>
        </div>
        <el-form-item label="摘要文本">
          <el-input v-model="form.summary_text" type="textarea" :rows="8" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveSummary">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { adminApi } from "../api/admin";

const activeTab = ref<"group" | "private">("group");
const loading = ref(false);
const saving = ref(false);
const detailVisible = ref(false);
const dialogVisible = ref(false);
const dialogMode = ref<"create" | "edit">("create");
const editingSummaryId = ref<number | null>(null);
const currentRow = ref<any>(null);
const summariesContentRef = ref<HTMLElement | null>(null);
const tabsRef = ref<any>(null);
const filterFormRef = ref<any>(null);
const paginationBarRef = ref<HTMLElement | null>(null);
const tableMaxHeightPx = ref(320);
let resizeObserver: ResizeObserver | null = null;
const rows = reactive({ items: [] as any[], page: 1, page_size: 20, total: 0 });
const groupSessions = ref<any[]>([]);
const privateSessions = ref<any[]>([]);
const filters = reactive({
  session_id: undefined as number | undefined,
  is_active: undefined as boolean | undefined,
});
const form = reactive({
  session_id: undefined as number | undefined,
  session_name: "",
  summary_text: "",
  created_by_model: "",
  source_start_message_id: undefined as number | undefined,
  source_end_message_id: undefined as number | undefined,
  source_message_count: 0,
  is_active: true,
});

const sessionNameMap = computed(() => {
  const source = activeTab.value === "group" ? groupSessions.value : privateSessions.value;
  return new Map(source.map((item) => [Number(item.session_id), item.display_name]));
});
const tableMaxHeight = computed(() => Math.max(220, tableMaxHeightPx.value));

const summarize = (value: string) => (value?.length > 100 ? `${value.slice(0, 100)}...` : value);

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

const displaySessionName = (row: any) =>
  row.session_name ||
  sessionNameMap.value.get(Number(row.session_id)) ||
  (activeTab.value === "group" ? `群聊 ${row.session_id}` : `QQ ${row.session_id}`);

const getElementHeight = (target: any) => {
  const el = target?.$el ?? target;
  return el instanceof HTMLElement ? el.offsetHeight : 0;
};

const recalcTableHeight = async () => {
  await nextTick();
  const container = summariesContentRef.value;
  if (!container) return;
  const top = container.getBoundingClientRect().top;
  const viewport = window.innerHeight;
  const tabsHeight = getElementHeight(tabsRef.value);
  const formHeight = getElementHeight(filterFormRef.value);
  const paginationHeight = getElementHeight(paginationBarRef.value);
  const available = viewport - top - 24;
  tableMaxHeightPx.value = available - tabsHeight - formHeight - paginationHeight - 18;
};

const loadData = async () => {
  loading.value = true;
  try {
    const params = { page: rows.page, page_size: rows.page_size, ...filters };
    const data =
      activeTab.value === "group"
        ? await adminApi.getGroupSummaries(params)
        : await adminApi.getPrivateSummaries(params);
    Object.assign(rows, data);
  } finally {
    loading.value = false;
  }
};

const loadSessionNames = async () => {
  const [groupRes, privateRes] = await Promise.all([
    adminApi.getGroupMessageSessions(),
    adminApi.getPrivateMessageSessions(),
  ]);
  groupSessions.value = groupRes.items || [];
  privateSessions.value = privateRes.items || [];
};

const handleSearch = async () => {
  rows.page = 1;
  await loadData();
  await recalcTableHeight();
};

const handlePageChange = async (page: number) => {
  rows.page = page;
  await loadData();
};

const handleTabChange = async () => {
  rows.page = 1;
  await loadData();
  await recalcTableHeight();
};

const openDetail = (row: any) => {
  currentRow.value = row;
  detailVisible.value = true;
};

const resetForm = () => {
  form.session_id = undefined;
  form.session_name = "";
  form.summary_text = "";
  form.created_by_model = "";
  form.source_start_message_id = undefined;
  form.source_end_message_id = undefined;
  form.source_message_count = 0;
  form.is_active = true;
};

const openCreateDialog = () => {
  dialogMode.value = "create";
  editingSummaryId.value = null;
  resetForm();
  dialogVisible.value = true;
};

const openEditDialog = (row: any) => {
  dialogMode.value = "edit";
  editingSummaryId.value = Number(row.id);
  form.session_id = Number(row.session_id);
  form.session_name = row.session_name || "";
  form.summary_text = row.summary_text || "";
  form.created_by_model = row.created_by_model || "";
  form.source_start_message_id = row.source_start_message_id ?? undefined;
  form.source_end_message_id = row.source_end_message_id ?? undefined;
  form.source_message_count = Number(row.source_message_count || 0);
  form.is_active = Boolean(row.is_active);
  dialogVisible.value = true;
};

const saveSummary = async () => {
  const payload = {
    session_id: form.session_id,
    session_name: form.session_name || undefined,
    summary_text: form.summary_text,
    created_by_model: form.created_by_model || undefined,
    source_start_message_id: form.source_start_message_id,
    source_end_message_id: form.source_end_message_id,
    source_message_count: form.source_message_count,
    is_active: form.is_active,
  };
  saving.value = true;
  try {
    if (dialogMode.value === "create") {
      if (activeTab.value === "group") {
        await adminApi.createGroupSummary(payload);
      } else {
        await adminApi.createPrivateSummary(payload);
      }
      ElMessage.success("摘要已创建");
    } else if (editingSummaryId.value != null) {
      if (activeTab.value === "group") {
        await adminApi.updateGroupSummary(editingSummaryId.value, payload);
      } else {
        await adminApi.updatePrivateSummary(editingSummaryId.value, payload);
      }
      ElMessage.success("摘要已更新");
    }
    dialogVisible.value = false;
    await loadData();
  } finally {
    saving.value = false;
  }
};

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除摘要版本 ${row.summary_version} 吗？`, "删除摘要", { type: "warning" });
  if (activeTab.value === "group") {
    await adminApi.deleteGroupSummary(Number(row.id));
  } else {
    await adminApi.deletePrivateSummary(Number(row.id));
  }
  ElMessage.success("摘要已删除");
  await loadData();
};

onMounted(async () => {
  resizeObserver = new ResizeObserver(() => {
    void recalcTableHeight();
  });
  window.addEventListener("resize", recalcTableHeight);
  await loadSessionNames();
  await loadData();
  await recalcTableHeight();
  if (summariesContentRef.value) resizeObserver.observe(summariesContentRef.value);
  const tabsEl = tabsRef.value?.$el;
  if (tabsEl instanceof HTMLElement) resizeObserver.observe(tabsEl);
  const filterEl = filterFormRef.value?.$el;
  if (filterEl instanceof HTMLElement) resizeObserver.observe(filterEl);
  if (paginationBarRef.value) resizeObserver.observe(paginationBarRef.value);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  window.removeEventListener("resize", recalcTableHeight);
});
</script>

<style scoped>
.summaries-content {
  display: flex;
  flex-direction: column;
}

.compact-filter-form {
  margin: 8px 0;
}

.table-scroll-shell {
  overflow: hidden;
}

.summary-pagination-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-height: 32px;
  margin-top: 6px;
  background: #fff;
}
</style>
