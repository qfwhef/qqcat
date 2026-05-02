import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import './style.css'

const savedTheme = localStorage.getItem('admin-theme-mode')
if (savedTheme === 'blue' || savedTheme === 'pink') {
  document.documentElement.setAttribute('data-theme', savedTheme)
} else {
  document.documentElement.setAttribute('data-theme', 'blue')
}

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { size: 'small' })

app.mount('#app')
