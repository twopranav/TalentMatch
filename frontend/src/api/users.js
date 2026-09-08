// frontend/src/api/users.js
import apiClient from './client'

export function fetchUsers(pending = false) {
  return apiClient.get('/users', { params: pending ? { pending: true } : {} }).then((res) => res.data)
}

export function setUserActive(userId, isActive) {
  return apiClient.patch(`/users/${userId}/active`, { is_active: isActive }).then((res) => res.data)
}

export function rejectRecruiterRequest(userId) {
  return apiClient.post(`/users/${userId}/reject-recruiter-request`).then((res) => res.data)
}

export function setUserRole(userId, role) {
  return apiClient.patch(`/users/${userId}/admin-status`, { role }).then((res) => res.data)
}

export function transferSuperuser(userId) {
  return apiClient.post(`/users/${userId}/transfer-superuser`).then((res) => res.data)
}

export function deleteUser(userId) {
  return apiClient.delete(`/users/${userId}`)
}