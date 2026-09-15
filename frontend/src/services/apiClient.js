import axios from 'axios'
import { API_BASE_URL } from '../config'

export const api = axios.create({ baseURL: API_BASE_URL, withCredentials: true, timeout: 15000 })
let csrfPromise
export function clearCsrf() { csrfPromise = undefined }
api.interceptors.request.use(async (config) => {
  if (!['get', 'head', 'options'].includes((config.method || 'get').toLowerCase())) {
    csrfPromise ??= api.get('/auth/csrf').then(({ data }) => data.token).catch((error) => {
      clearCsrf()
      throw error
    })
    config.headers['X-CSRF-Token'] = await csrfPromise
  }
  return config
})
api.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401) window.dispatchEvent(new Event('session:expired'))
  if (error.response?.status === 400) clearCsrf()
  return Promise.reject(error)
})
