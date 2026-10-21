import { expect, it } from 'vitest'
import { loginSchema, registerSchema, safeReturnPath } from './contracts'

it('valida registro y no acepta contraseñas cortas ni email inválido', () => {
  const valid = { username: 'niche', full_name: 'Niche', email: 'qa@example.test', password: '12345678', account_type: 'public' }
  expect(registerSchema.safeParse(valid).success).toBe(true)
  expect(registerSchema.safeParse({ ...valid, password: 'short' }).success).toBe(false)
  expect(registerSchema.safeParse({ ...valid, email: 'invalid' }).success).toBe(false)
  expect(registerSchema.safeParse({ ...valid, account_type: 'admin' }).success).toBe(false)
})
it('login no modifica la contraseña', () => {
  expect(loginSchema.parse({ username: ' niche ', password: ' padded ' })).toEqual({ username: 'niche', password: ' padded ' })
})
it.each(['https://evil.test', '//evil.test', '/\\evil.test', '/login', null])('evita redirección insegura a %s', (path) => {
  expect(safeReturnPath(path)).toBe('/')
})
it('permite regresar a una operación local', () => {
  expect(safeReturnPath('/operaciones/123')).toBe('/operaciones/123')
})
