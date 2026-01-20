export interface ApiResponse<T> {
  success: boolean
  data: T
  message?: string
}

export interface ApiListResponse<T> {
  success: boolean
  data: T[]
  total: number
}

export interface ApiError {
  success: false
  error: string
  detail: string
}

export interface PaginationParams {
  page?: number
  limit?: number
}

export interface NodeFilterParams extends PaginationParams {
  state?: string
  group_id?: string
  tag?: string
  search?: string
}
