import { z } from 'zod'

export const userSchema = z.object({
  id: z.guid(), username: z.string(), full_name: z.string(), biography: z.string().nullable(),
  account_type: z.enum(['public', 'private']), account_status: z.enum(['active', 'suspended']),
  registered_at: z.string(), role: z.enum(['user', 'moderator', 'admin']),
})
export type User = z.infer<typeof userSchema>

export const loginSchema = z.object({
  username: z.string().trim().min(3, 'Usá al menos 3 caracteres.').max(50, 'Máximo 50 caracteres.'),
  password: z.string().min(1, 'Ingresá tu contraseña.').max(128, 'Máximo 128 caracteres.'),
})
export const registerSchema = loginSchema.extend({
  full_name: z.string().trim().min(1, 'Ingresá tu nombre.').max(150, 'Máximo 150 caracteres.'),
  email: z.email('Ingresá un email válido.'),
  password: z.string().min(8, 'Usá al menos 8 caracteres.').max(128, 'Máximo 128 caracteres.'),
  account_type: z.enum(['public', 'private']),
})
export type LoginValues = z.infer<typeof loginSchema>
export type RegisterValues = z.infer<typeof registerSchema>

export function safeReturnPath(value: unknown): string {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') && !value.includes('\\')
    && !/^\/(login|registro)(\/|\?|$)/.test(value) ? value : '/'
}
