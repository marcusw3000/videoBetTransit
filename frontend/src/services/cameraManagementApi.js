import { api } from './apiClient'

export const getCameraManagement = () => api.get('/admin/camera-management')
export const activateCameraManagement = payload => api.post('/admin/camera-management/activate', payload)
export const updateCameraManagementDraft = payload => api.put('/admin/camera-management/draft', payload)
export const applyCameraManagement = () => api.post('/admin/camera-management/apply')
export const deactivateCameraManagement = () => api.post('/admin/camera-management/deactivate')
