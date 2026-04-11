import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory('/admin-ui/'),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('../layouts/AdminLayout.vue'),
      redirect: '/overview',
      children: [
        { path: 'overview', name: 'overview', component: () => import('../views/OverviewView.vue') },
        {
          path: 'scheduled-tasks',
          name: 'scheduled-tasks',
          component: () => import('../views/ScheduledTasksView.vue'),
        },
        { path: 'runtime', name: 'runtime', component: () => import('../views/RuntimeConfigView.vue') },
        { path: 'tools', name: 'tools', component: () => import('../views/ToolsView.vue') },
        { path: 'prompts', name: 'prompts', component: () => import('../views/PromptsView.vue') },
        { path: 'access', name: 'access', component: () => import('../views/AccessView.vue') },
        {
          path: 'session-configs',
          name: 'session-configs',
          component: () => import('../views/SessionConfigsView.vue'),
        },
        { path: 'messages', redirect: '/messages/group' },
        { path: 'messages/group', name: 'messages-group', component: () => import('../views/MessagesView.vue') },
        {
          path: 'messages/private',
          name: 'messages-private',
          component: () => import('../views/MessagesView.vue'),
        },
        { path: 'summaries', name: 'summaries', component: () => import('../views/SummariesView.vue') },
        { path: 'ai-calls', name: 'ai-calls', component: () => import('../views/AICallsView.vue') },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  if (to.meta.public) {
    if (to.path === '/login' && !authStore.checked) {
      try {
        await authStore.fetchMe()
        return '/overview'
      } catch {
        return true
      }
    }
    return true
  }
  try {
    await authStore.fetchMe()
    return true
  } catch {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }
})

export default router
