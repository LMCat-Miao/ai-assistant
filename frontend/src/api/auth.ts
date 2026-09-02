import request from "@/utils/request"

export function login(username: string, password: string) {
  return request.post("/api/auth/login", {
    username,
    password,
  })
}