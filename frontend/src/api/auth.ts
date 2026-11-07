import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'
import type { AxiosResponse } from 'axios'

export function login(username: string, password: string) {
  return request.post('/api/auth/login', {
    username,
    password,
  })
}

/** 发送注册邮箱验证码 */
export interface SendRegisterCodePayload {
  email: string
}

export interface SendRegisterCodeData {
  expires_in: number
}

export function sendRegisterCode(
  payload: SendRegisterCodePayload,
): Promise<AxiosResponse<ApiResponse<SendRegisterCodeData>>> {
  return request.post('/api/auth/email/send-code', payload)
}

/** 邮箱验证码注册（成功不返回 Token） */
export interface RegisterPayload {
  email: string
  code: string
  username: string
  password: string
}

export interface RegisterData {
  user_id: number
  username: string
}

export function register(
  payload: RegisterPayload,
): Promise<AxiosResponse<ApiResponse<RegisterData>>> {
  return request.post('/api/auth/register', payload)
}
