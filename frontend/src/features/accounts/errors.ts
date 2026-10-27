import { ZodError } from 'zod'
import { ApiError } from '../../services/http/client'

export function accountError(error: Error): string {
  if (error instanceof ZodError) return 'La respuesta de la cuenta no tiene el formato esperado. Volvé a consultar o avisá al equipo administrador.'
  if (error instanceof ApiError) {
    if (error.status === 403) return 'La trazabilidad es privada. Solo el titular, un moderador o un administrador pueden consultarla.'
    if (error.status === 404) return 'No encontramos esa cuenta u operación.'
    if (error.status === 409) return 'El estado de la cuenta cambió o existe otra operación en curso. Actualizá la cuenta antes de continuar.'
    if (error.status === 503) return 'No se pudo obtener la información completa de la cuenta. Volvé a intentar cuando los servicios estén disponibles.'
  }
  return error.message
}
