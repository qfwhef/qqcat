<template>
  <div>
    <div class="page-header">
      <div class="page-title">提示词管理</div>
      <div>
        <el-button :loading="loading" @click="loadData">刷新</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存提示词</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="基础人格" name="prompt_base">
        <PromptEditor title="基础人格提示词" field="prompt_base" v-model="form.prompt_base" :default-value="defaults.prompt_base" @reset="resetField" />
      </el-tab-pane>
      <el-tab-pane label="私聊逻辑" name="prompt_logic_private">
        <PromptEditor title="私聊逻辑提示词" field="prompt_logic_private" v-model="form.prompt_logic_private" :default-value="defaults.prompt_logic_private" @reset="resetField" />
      </el-tab-pane>
      <el-tab-pane label="@我逻辑" name="prompt_logic_at_me">
        <PromptEditor title="@机器人逻辑提示词" field="prompt_logic_at_me" v-model="form.prompt_logic_at_me" :default-value="defaults.prompt_logic_at_me" @reset="resetField" />
      </el-tab-pane>
      <el-tab-pane label="群聊逻辑" name="prompt_logic_group">
        <PromptEditor title="群聊逻辑提示词" field="prompt_logic_group" v-model="form.prompt_logic_group" :default-value="defaults.prompt_logic_group" @reset="resetField" />
      </el-tab-pane>
      <el-tab-pane label="摘要系统" name="prompt_summary_system">
        <PromptEditor title="摘要系统提示词" field="prompt_summary_system" v-model="form.prompt_summary_system" :default-value="defaults.prompt_summary_system" @reset="resetField" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { defineComponent, h, reactive, ref } from 'vue'
import { ElButton, ElCard, ElInput, ElMessage, ElSpace, ElTag } from 'element-plus'

import { adminApi } from '../api/admin'

type PromptField =
  | 'prompt_base'
  | 'prompt_logic_private'
  | 'prompt_logic_at_me'
  | 'prompt_logic_group'
  | 'prompt_summary_system'

const activeTab = ref<PromptField>('prompt_base')
const loading = ref(false)
const saving = ref(false)
const form = reactive<Record<PromptField, string>>({
  prompt_base: '',
  prompt_logic_private: '',
  prompt_logic_at_me: '',
  prompt_logic_group: '',
  prompt_summary_system: '',
})
const defaults = reactive<Record<PromptField, string>>({
  prompt_base: '',
  prompt_logic_private: '',
  prompt_logic_at_me: '',
  prompt_logic_group: '',
  prompt_summary_system: '',
})

const PromptEditor = defineComponent({
  props: {
    title: { type: String, required: true },
    field: { type: String, required: true },
    modelValue: { type: String, required: true },
    defaultValue: { type: String, required: true },
  },
  emits: ['update:modelValue', 'reset'],
  setup(props, { emit }) {
    return () =>
      h(ElCard, { class: 'page-card' }, () => [
        h('div', { class: 'table-toolbar' }, [
          h('div', [
            h('div', { style: 'font-size:16px;font-weight:700;color:#111827' }, props.title),
            h('div', { style: 'margin-top:6px;color:#64748b;font-size:13px' }, '修改后会写入数据库并即时生效'),
          ]),
          h(ElSpace, {}, () => [
            h(ElTag, { type: 'info' }, () => `默认长度 ${props.defaultValue.length}`),
            h(
              ElButton,
              {
                onClick: () => emit('reset', props.field),
              },
              () => '重置为默认值',
            ),
          ]),
        ]),
        h(ElInput, {
          modelValue: props.modelValue,
          'onUpdate:modelValue': (value: string) => emit('update:modelValue', value),
          type: 'textarea',
          rows: 18,
          placeholder: '编辑提示词正文',
        }),
      ])
  },
})

const loadData = async () => {
  loading.value = true
  try {
    const [current, promptDefaults] = await Promise.all([adminApi.getPrompts(), adminApi.getPromptDefaults()])
    ;(Object.keys(form) as PromptField[]).forEach((key) => {
      form[key] = current[key] || ''
      defaults[key] = promptDefaults[key] || ''
    })
  } finally {
    loading.value = false
  }
}

const resetField = (field: PromptField) => {
  form[field] = defaults[field]
}

const save = async () => {
  saving.value = true
  try {
    await adminApi.updatePrompts({ ...form })
    ElMessage.success('提示词已更新')
    await loadData()
  } finally {
    saving.value = false
  }
}

loadData()
</script>
