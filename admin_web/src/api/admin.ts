import http from './http'

export interface PagedResult<T = any> {
  items: T[]
  page: number
  page_size: number
  total: number
}

const cleanParams = (params: Record<string, unknown>) =>
  Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== '' && value !== null && value !== undefined),
  )

export const adminApi = {
  login(payload: { qq: number; token: string }) {
    return http.post('/auth/login', payload).then((res) => res.data)
  },
  logout() {
    return http.post('/auth/logout').then((res) => res.data)
  },
  me() {
    return http.get('/auth/me').then((res) => res.data)
  },
  getOverview() {
    return http.get('/overview').then((res) => res.data)
  },
  getScheduledTasks(params: Record<string, unknown>) {
    return http.get<PagedResult>('/scheduled-tasks', { params: cleanParams(params) }).then((res) => res.data)
  },
  createScheduledTask(payload: Record<string, unknown>) {
    return http.post('/scheduled-tasks', payload).then((res) => res.data)
  },
  updateScheduledTask(taskId: number, payload: Record<string, unknown>) {
    return http.put(`/scheduled-tasks/${taskId}`, payload).then((res) => res.data)
  },
  deleteScheduledTask(taskId: number) {
    return http.delete(`/scheduled-tasks/${taskId}`).then((res) => res.data)
  },
  runScheduledTaskNow(taskId: number) {
    return http.post(`/scheduled-tasks/${taskId}/run`).then((res) => res.data)
  },
  getRuntimeConfig() {
    return http.get('/runtime-config').then((res) => res.data)
  },
  updateRuntimeConfig(payload: Record<string, unknown>) {
    return http.put('/runtime-config', payload).then((res) => res.data)
  },
  getPrompts() {
    return http.get('/prompts').then((res) => res.data)
  },
  getPromptDefaults() {
    return http.get('/prompts/defaults').then((res) => res.data)
  },
  updatePrompts(payload: Record<string, unknown>) {
    return http.put('/prompts', payload).then((res) => res.data)
  },
  getSecrets() {
    return http.get<PagedResult>('/secrets').then((res) => res.data)
  },
  getTools() {
    return http.get<PagedResult>('/tools').then((res) => res.data)
  },
  createHttpTool(payload: Record<string, unknown>) {
    return http.post('/tools/http', payload).then((res) => res.data)
  },
  updateTool(toolName: string, payload: Record<string, unknown>) {
    return http.put(`/tools/${toolName}`, payload).then((res) => res.data)
  },
  deleteTool(toolName: string) {
    return http.delete(`/tools/${toolName}`).then((res) => res.data)
  },
  updateSecret(secretKey: string, payload: { secret_value: string; value_hint?: string }) {
    return http.put(`/secrets/${secretKey}`, payload).then((res) => res.data)
  },
  getAdminUsers() {
    return http.get<PagedResult>('/admin-users').then((res) => res.data)
  },
  createAdminUser(payload: { user_id: number; nickname?: string; is_active: boolean }) {
    return http.post('/admin-users', payload).then((res) => res.data)
  },
  updateAdminUser(userId: number, payload: { nickname?: string; is_active?: boolean }) {
    return http.put(`/admin-users/${userId}`, payload).then((res) => res.data)
  },
  getBlocklist() {
    return http.get('/blocklist').then((res) => res.data)
  },
  updateBlocklist(payload: { blocked_groups?: number[]; blocked_users?: number[] }) {
    return http.put('/blocklist', payload).then((res) => res.data)
  },
  getGroupConfigs(params: Record<string, unknown>) {
    return http.get<PagedResult>('/group-configs', { params: cleanParams(params) }).then((res) => res.data)
  },
  updateGroupConfig(groupId: number, payload: Record<string, unknown>) {
    return http.put(`/group-configs/${groupId}`, payload).then((res) => res.data)
  },
  getPrivateConfigs(params: Record<string, unknown>) {
    return http.get<PagedResult>('/private-configs', { params: cleanParams(params) }).then((res) => res.data)
  },
  updatePrivateConfig(userId: number, payload: Record<string, unknown>) {
    return http.put(`/private-configs/${userId}`, payload).then((res) => res.data)
  },
  getGroupMessages(params: Record<string, unknown>) {
    return http.get<PagedResult>('/messages/group', { params: cleanParams(params) }).then((res) => res.data)
  },
  getGroupMessageDetail(sessionId: number, messageId: number) {
    return http.get(`/messages/group/${sessionId}/${messageId}`).then((res) => res.data)
  },
  updateGroupMessage(sessionId: number, messageId: number, payload: Record<string, unknown>) {
    return http.put(`/messages/group/${sessionId}/${messageId}`, payload).then((res) => res.data)
  },
  deleteGroupMessages(sessionId: number, messageIds: number[]) {
    return http.post(`/messages/group/${sessionId}/batch-delete`, { message_ids: messageIds }).then((res) => res.data)
  },
  clearGroupMessages(sessionId: number) {
    return http.post(`/messages/group/${sessionId}/clear`).then((res) => res.data)
  },
  getGroupMessageSessions(params: Record<string, unknown> = {}) {
    return http.get<PagedResult>('/message-sessions/group', { params: cleanParams(params) }).then((res) => res.data)
  },
  getPrivateMessages(params: Record<string, unknown>) {
    return http.get<PagedResult>('/messages/private', { params: cleanParams(params) }).then((res) => res.data)
  },
  getPrivateMessageDetail(sessionId: number, messageId: number) {
    return http.get(`/messages/private/${sessionId}/${messageId}`).then((res) => res.data)
  },
  updatePrivateMessage(sessionId: number, messageId: number, payload: Record<string, unknown>) {
    return http.put(`/messages/private/${sessionId}/${messageId}`, payload).then((res) => res.data)
  },
  deletePrivateMessages(sessionId: number, messageIds: number[]) {
    return http.post(`/messages/private/${sessionId}/batch-delete`, { message_ids: messageIds }).then((res) => res.data)
  },
  clearPrivateMessages(sessionId: number) {
    return http.post(`/messages/private/${sessionId}/clear`).then((res) => res.data)
  },
  getPrivateMessageSessions(params: Record<string, unknown> = {}) {
    return http.get<PagedResult>('/message-sessions/private', { params: cleanParams(params) }).then((res) => res.data)
  },
  getGroupSummaries(params: Record<string, unknown>) {
    return http.get<PagedResult>('/summaries/group', { params: cleanParams(params) }).then((res) => res.data)
  },
  getPrivateSummaries(params: Record<string, unknown>) {
    return http.get<PagedResult>('/summaries/private', { params: cleanParams(params) }).then((res) => res.data)
  },
  getAiCallLogs(params: Record<string, unknown>) {
    return http.get<PagedResult>('/ai-call-logs', { params: cleanParams(params) }).then((res) => res.data)
  },
}
