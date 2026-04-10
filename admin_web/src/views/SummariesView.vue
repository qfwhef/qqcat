<template>
  <div>
    <div class="page-header">
      <div class="page-title">摘要查询</div>
    </div>

    <el-card class="page-card">
      <el-tabs v-model="activeTab" @tab-change="loadData">
        <el-tab-pane label="群聊摘要" name="group" />
        <el-tab-pane label="私聊摘要" name="private" />
      </el-tabs>
      <el-form :inline="true" class="toolbar-form">
        <el-form-item label="会话 ID">
          <el-input
            v-model.number="filters.session_id"
            placeholder="群号/用户QQ"
            style="width: 180px"
            clearable
          />
        </el-form-item>
        <el-form-item label="是否活跃">
          <el-select v-model="filters.is_active" clearable style="width: 120px">
            <el-option label="是" :value="true" />
            <el-option label="否" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadData"
            >查询</el-button
          >
        </el-form-item>
      </el-form>
      <el-table :data="rows.items" @row-click="openDetail">
        <el-table-column label="群名 / QQ昵称" min-width="180">
          <template #default="{ row }">
            {{ displaySessionName(row) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="session_id"
          label="群号 / QQ号"
          min-width="140"
        />
        <el-table-column prop="summary_version" label="摘要版本" width="100" />
        <el-table-column label="摘要内容" min-width="320">
          <template #default="{ row }">{{
            summarize(row.summary_text)
          }}</template>
        </el-table-column>
        <el-table-column label="活跃" width="90">
          <template #default="{ row }">{{
            row.is_active ? "是" : "否"
          }}</template>
        </el-table-column>
        <el-table-column prop="created_by_model" label="模型" min-width="160" />
        <el-table-column
          prop="source_start_message_id"
          label="起始消息ID"
          min-width="120"
        />
        <el-table-column
          prop="source_end_message_id"
          label="结束消息ID"
          min-width="120"
        />
        <el-table-column prop="created_at" label="创建时间" min-width="160" />
      </el-table>
      <div style="display: flex; justify-content: flex-end; margin-top: 16px">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="rows.total"
          :page-size="rows.page_size"
          :current-page="rows.page"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <el-drawer v-model="detailVisible" title="摘要详情" size="50%">
      <el-descriptions v-if="currentRow" :column="2" border>
        <el-descriptions-item label="群名 / QQ昵称">
          {{ displaySessionName(currentRow) }}
        </el-descriptions-item>
        <el-descriptions-item label="会话ID">{{
          currentRow.session_id
        }}</el-descriptions-item>
        <el-descriptions-item label="摘要版本">{{
          currentRow.summary_version
        }}</el-descriptions-item>
        <el-descriptions-item label="起始消息">{{
          currentRow.source_start_message_id || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="结束消息">{{
          currentRow.source_end_message_id || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="覆盖消息数">{{
          currentRow.source_message_count
        }}</el-descriptions-item>
        <el-descriptions-item label="当前摘要版本">{{
          currentRow.current_summary_version || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="最后消息ID">{{
          currentRow.last_message_id || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="最后摘要消息ID">{{
          currentRow.last_summary_message_id || "-"
        }}</el-descriptions-item>
        <el-descriptions-item label="摘要冷却截止">{{
          currentRow.summary_cooldown_until || "-"
        }}</el-descriptions-item>
      </el-descriptions>
      <el-divider content-position="left">摘要文本</el-divider>
      <pre class="json-block">{{ currentRow?.summary_text || "" }}</pre>
      <el-divider content-position="left">结构化摘要</el-divider>
      <pre class="json-block">{{ formatJson(currentRow?.summary_json) }}</pre>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import { adminApi } from "../api/admin";

const activeTab = ref<"group" | "private">("group");
const loading = ref(false);
const detailVisible = ref(false);
const currentRow = ref<any>(null);
const rows = reactive({ items: [] as any[], page: 1, page_size: 20, total: 0 });
const groupSessions = ref<any[]>([]);
const privateSessions = ref<any[]>([]);
const filters = reactive({
  session_id: undefined as number | undefined,
  is_active: undefined as boolean | undefined,
});

const sessionNameMap = computed(() => {
  const source =
    activeTab.value === "group" ? groupSessions.value : privateSessions.value;
  return new Map(
    source.map((item) => [Number(item.session_id), item.display_name]),
  );
});

const summarize = (value: string) =>
  value?.length > 100 ? `${value.slice(0, 100)}...` : value;

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
  (activeTab.value === "group"
    ? `群聊 ${row.session_id}`
    : `QQ ${row.session_id}`);

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

const handlePageChange = async (page: number) => {
  rows.page = page;
  await loadData();
};

const openDetail = (row: any) => {
  currentRow.value = row;
  detailVisible.value = true;
};

onMounted(async () => {
  await loadSessionNames();
  await loadData();
});
</script>
