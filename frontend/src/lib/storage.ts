export const storage = {
  get(key: string): string | null {
    try { return sessionStorage.getItem(key) } catch { return null }
  },
  set(key: string, value: string): void {
    try { sessionStorage.setItem(key, value) } catch { /* The current tab still works without persistence. */ }
  },
  remove(key: string): void {
    try { sessionStorage.removeItem(key) } catch { /* Storage may be disabled by browser policy. */ }
  },
}
