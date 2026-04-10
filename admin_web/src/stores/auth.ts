import { defineStore } from 'pinia'

import { adminApi } from '../api/admin'

interface AdminUser {
  user_id: number | null
  nickname: string
  auth_mode: string
}

interface MenuItem {
  key: string
  label: string
  path: string
}

export const useAuthStore = defineStore('admin-auth', {
  state: () => ({
    user: null as AdminUser | null,
    menus: [] as MenuItem[],
    checked: false,
  }),
  getters: {
    isLoggedIn(state) {
      return Boolean(state.user)
    },
  },
  actions: {
    async fetchMe(force = false) {
      if (this.checked && !force) {
        return this.user
      }
      try {
        const data = await adminApi.me()
        this.user = data.user
        this.menus = data.menus || []
        this.checked = true
        return this.user
      } catch (error) {
        this.user = null
        this.menus = []
        this.checked = true
        throw error
      }
    },
    async login(payload: { qq: number; token: string }) {
      const data = await adminApi.login(payload)
      this.user = data.user
      this.menus = data.menus || []
      this.checked = true
      return data
    },
    async logout() {
      await adminApi.logout()
      this.user = null
      this.menus = []
      this.checked = true
    },
  },
})
