import axios from 'axios'

// One client for every backend call, so VITE_API_BASE_URL moves all of them together.
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000/api',
})

// A readable message for a failed call: the backend's own string when it sent one.
export function errorMessage (action: string, error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (typeof error.response?.data === 'string' && error.response.data) {
      return `${action}: ${error.response.data}`
    }
    if (!error.response) return `${action}: the backend did not answer. Check that it is running.`
  }
  return `${action}. Try again.`
}
