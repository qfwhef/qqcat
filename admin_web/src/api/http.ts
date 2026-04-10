import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: '/admin',
  withCredentials: true,
  timeout: 15000,
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error?.response?.data?.detail
    const message = Array.isArray(detail)
      ? detail
          .map((item) => item?.msg || item?.message || JSON.stringify(item))
          .join('；')
      : detail || error?.message || '请求失败'
    if (error?.response?.status !== 401) {
      ElMessage.error(String(message))
    }
    return Promise.reject(error)
  },
)

export default http
