import { ApiError } from '../../services/http/client'
import { ZodError } from 'zod'

export function moderationError(error: Error): string {
  if (error instanceof ZodError) return 'La respuesta del servidor no tiene el formato esperado. Volvé a consultar; si persiste, avisá al equipo administrador.'
  if (error instanceof ApiError) {
    if (error.status === 403) return 'No tenés permiso para consultar o modificar este reporte.'
    if (error.status === 404) return 'El reporte o la publicación no están disponibles.'
    if (error.status === 409) return 'La solicitud entra en conflicto con el estado actual: puede existir un reporte tuyo, una decisión previa o una operación en curso. Actualizá antes de continuar.'
  }
  return error.message
}
