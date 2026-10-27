import { randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { z } from 'zod'
import { jobSchema, reportSchema } from '../../src/features/moderation/contracts'
import { postSchema } from '../../src/features/posts/contracts'

test.setTimeout(90_000)
const root = fileURLToPath(new URL('../../../', import.meta.url))
async function account(request: APIRequestContext, role: 'user' | 'moderator' | 'admin' = 'user') {
  const username = `qa_p7_${randomUUID().replaceAll('-', '').slice(0, 20)}`
  const password = `Qa!${randomUUID()}`
  const response = await request.post('/backend/api/v1/users', { data: { username, password, full_name: `QA Moderación ${role}`, email: `${username}@example.test`, account_type: 'public' } })
  expect(response.status()).toBe(201)
  const id = z.object({ id: z.uuid() }).parse(await response.json()).id
  if (role !== 'user') {
    // Roles are not granted by registration. Provision ONLY this new isolated QA account.
    const code = `import asyncio
from pymongo import AsyncMongoClient
from app.core.config import get_settings
async def main():
    settings = get_settings()
    assert settings.app_env == 'development'
    client = AsyncMongoClient(settings.mongodb_url)
    try:
        result = await client[settings.mongodb_database].users.update_one({'_id': '${id}', 'username': '${username}', 'role': 'user'}, {'$set': {'role': '${role}'}})
        assert result.modified_count == 1
    finally:
        await client.close()
asyncio.run(main())`
    execFileSync('docker', ['compose', 'exec', '-T', 'api', 'python', '-c', code], { cwd: root, timeout: 20_000, stdio: 'pipe' })
  }
  const login = await request.post('/backend/api/v1/users/login', { data: { username, password } })
  expect(login.status()).toBe(200)
  const token = z.object({ access_token: z.string() }).parse(await login.json()).access_token
  return { username, password, id, headers: { Authorization: `Bearer ${token}` } }
}
type Actor = Awaited<ReturnType<typeof account>>
async function waitOperation(request: APIRequestContext, path: string, actor: Actor) {
  await expect.poll(async () => {
    const response = await request.get(`/backend/api/v1/${path}`, { headers: actor.headers })
    expect(response.ok()).toBeTruthy()
    return z.object({ status: z.string() }).parse(await response.json()).status
  }, { timeout: 25_000 }).toBe('completed')
}
async function publish(request: APIRequestContext, author: Actor, text: string) {
  const response = await request.post('/backend/api/v1/posts', { headers: { ...author.headers, 'Idempotency-Key': randomUUID() }, data: { user_id: author.id, text, media: [], interests: ['datos'], visibility: 'public' } })
  expect(response.status()).toBe(202)
  const job = z.object({ operation_id: z.uuid(), post_id: z.uuid() }).parse(await response.json())
  await waitOperation(request, `problems/operations/${job.operation_id}`, author)
  return job.post_id
}
async function login(page: Page, actor: Actor) {
  await page.goto('/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(actor.username)
  await page.getByLabel('Contraseña', { exact: true }).fill(actor.password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.locator('.session-name')).toHaveText(`@${actor.username}`)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
}
async function decision(page: Page, action: string, reason: string) {
  await page.getByRole('button', { name: action === 'hide' ? 'Ocultar publicación' : action === 'reject' ? 'Rechazar reporte' : 'Revertir ocultamiento', exact: true }).click()
  await page.getByLabel('Motivo de la decisión', { exact: true }).fill(reason)
  await page.getByRole('button', { name: action === 'hide' ? 'Confirmar ocultamiento' : action === 'reject' ? 'Confirmar rechazo' : 'Confirmar reversión', exact: true }).click()
  await expect(page.getByText(action === 'hide' ? 'Ocultado' : action === 'reject' ? 'Reporte rechazado' : 'Restaurado', { exact: true })).toBeVisible({ timeout: 25_000 })
  await expect(page.getByText('La operación terminó y su resultado fue confirmado.', { exact: true })).toBeVisible({ timeout: 25_000 })
}

test('P7 reporte desde feed, ocultación y restauración real con historial y contadores', async ({ page, request }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error' && !message.text().includes('404')) errors.push(message.text()) })
  const author = await account(request)
  const reader = await account(request)
  const moderator = await account(request, 'moderator')
  const followed = await request.post('/backend/api/v1/social/follows', { headers: reader.headers, data: { user_id: reader.id, followed_user_id: author.id } })
  expect(followed.status()).toBe(202)
  const followId = z.object({ operation_id: z.uuid() }).parse(await followed.json()).operation_id
  await waitOperation(request, `social/operations/${followId}`, reader)
  const text = `Contenido QA P7 ${randomUUID()}`
  const postId = await publish(request, author, text)
  const reaction = await request.post('/backend/api/v1/problems/5/reaction', { data: { post_id: postId, user_id: reader.id, kind: 'like' } })
  expect(reaction.status()).toBe(202)
  const comment = await request.post('/backend/api/v1/problems/5/comment', { data: { post_id: postId, user_id: reader.id, text: 'Comentario QA preservado' }, headers: { 'Idempotency-Key': randomUUID() } })
  expect(comment.status()).toBe(202)
  await login(page, reader)
  await expect(page.getByText(text, { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Reportar publicación', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Reportar publicación' })).toBeVisible()
  await page.getByLabel('Contanos qué pasó (opcional)').fill(`Revisar este contenido ${reader.username}`)
  await page.screenshot({ path: info.outputPath('p7-report.png'), fullPage: true })
  await page.getByRole('button', { name: 'Enviar reporte' }).click()
  await expect(page.getByRole('heading', { name: 'Detalle del reporte' })).toBeVisible()
  const reportPath = new URL(page.url()).pathname
  await expect(page.getByText('Pendiente', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Resolver reporte' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await login(page, moderator)
  await page.getByRole('link', { name: 'Moderación', exact: true }).click()
  await page.locator(`a[href="${reportPath}"]`).click()
  await expect(page.getByText(text, { exact: true })).toBeVisible()
  await expect.poll(async () => postSchema.parse(await (await request.get(`/backend/api/v1/posts/${postId}`)).json()).comment_count).toBe(1)
  await decision(page, 'hide', 'Spam confirmado por QA')
  await page.reload()
  await expect(page.getByText('La operación terminó y su resultado fue confirmado.', { exact: true })).toBeVisible()
  expect((await request.get(`/backend/api/v1/posts/${postId}`)).status()).toBe(404)
  const feedHidden = await request.get(`/backend/api/v1/feeds/${reader.id}`, { headers: reader.headers })
  expect(z.object({ items: z.array(postSchema) }).parse(await feedHidden.json()).items).toHaveLength(0)
  const state = await request.get(`/backend/api/v1/moderation/posts/${postId}/state`, { headers: moderator.headers })
  expect(z.object({ feeds: z.record(z.string(), z.number()), counters: z.record(z.string(), z.number()) }).parse(await state.json())).toEqual({ feeds: {}, counters: { post_reactions: 0, post_comments: 0 } })
  await page.reload()
  await expect(page.getByText('Ocultado', { exact: true })).toBeVisible()
  await expect(page.getByText('Spam confirmado por QA', { exact: true }).first()).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: info.outputPath('p7-hidden.png'), fullPage: true })
  await decision(page, 'revert', 'Revisión: publicación permitida')
  const restored = await request.get(`/backend/api/v1/posts/${postId}`)
  expect(postSchema.parse(await restored.json())).toMatchObject({ reaction_count: 1, comment_count: 1 })
  await page.reload()
  await expect(page.getByText('Restaurado', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Resolver reporte' })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('p7-restored.png'), fullPage: true })
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await login(page, reader)
  await expect(page.getByText(text, { exact: true })).toBeVisible()
  await expect(page.getByText('1 reacciones · 1 comentarios')).toBeVisible()
  await page.goto(reportPath)
  await expect(page.getByText('Restaurado', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Historial de la publicación' })).toHaveCount(0)
  expect(errors).toEqual([])
})

test('P7 admin rechaza sin ocultar; usuario común y tercero no acceden a datos privados', async ({ page, request }, info) => {
  const author = await account(request)
  const reporter = await account(request)
  const admin = await account(request, 'admin')
  const text = `Publicación permitida ${randomUUID()}`
  const postId = await publish(request, author, text)
  const created = await request.post('/backend/api/v1/moderation/reports', { headers: reporter.headers, data: { post_id: postId, reason: 'other', description: 'Revisión administrativa QA' } })
  expect(created.status()).toBe(201)
  const report = reportSchema.parse(await created.json())
  expect((await request.post('/backend/api/v1/moderation/reports', { headers: reporter.headers, data: { post_id: postId, reason: 'spam' } })).status()).toBe(409)
  expect((await request.get('/backend/api/v1/moderation/reports', { headers: reporter.headers })).status()).toBe(403)
  expect((await request.get(`/backend/api/v1/moderation/reports/${report.id}`, { headers: author.headers })).status()).toBe(403)
  expect((await request.post(`/backend/api/v1/moderation/reports/${report.id}/decision`, { headers: reporter.headers, data: { decision: 'hide', reason: 'No permitido' } })).status()).toBe(403)
  await login(page, reporter)
  await expect(page.getByRole('link', { name: 'Moderación', exact: true })).toHaveCount(0)
  await page.goto('/moderacion')
  await expect(page.getByRole('heading', { name: 'Acceso restringido' })).toBeVisible()
  await page.getByRole('button', { name: 'Cerrar sesión' }).click()
  await login(page, admin)
  await page.goto(`/reportes/${report.id}`)
  await decision(page, 'reject', 'No infringe las normas')
  expect((await request.get(`/backend/api/v1/posts/${postId}`)).status()).toBe(200)
  await page.reload()
  await expect(page.getByText('Reporte rechazado', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Revisar decisión' })).toHaveCount(0)
  await page.getByRole('link', { name: 'Volver a moderación' }).click()
  await page.getByLabel('Estado de los reportes').selectOption('rejected')
  await expect(page.locator(`a[href="/reportes/${report.id}"]`)).toBeVisible()
  await page.screenshot({ path: info.outputPath('p7-queue.png'), fullPage: true })
})

test('P7 compensación real se muestra sin falso éxito', async ({ page, request }, info) => {
  const author = await account(request)
  const reporter = await account(request)
  const moderator = await account(request, 'moderator')
  const postId = await publish(request, author, `QA compensación P7 ${randomUUID()}`)
  const created = await request.post('/backend/api/v1/moderation/reports', { headers: reporter.headers, data: { post_id: postId, reason: 'spam' } })
  expect(created.status()).toBe(201)
  const report = reportSchema.parse(await created.json())
  const response = await request.post(`/backend/api/v1/moderation/reports/${report.id}/decision`, { headers: { ...moderator.headers, 'X-Fail-At-Step': 'mongo_hide' }, data: { decision: 'hide', reason: 'Falla de prueba QA' } })
  expect(response.status()).toBe(202)
  const job = jobSchema.parse(await response.json())
  await login(page, moderator)
  await page.goto(`/moderacion/operaciones/${job.operation_id}`)
  await expect(page.getByText('Decisión cancelada', { exact: true })).toBeVisible({ timeout: 25_000 })
  await expect(page.getByText('Decisión completada', { exact: true })).toHaveCount(0)
  expect((await request.get(`/backend/api/v1/posts/${postId}`)).status()).toBe(200)
  expect(reportSchema.parse(await (await request.get(`/backend/api/v1/moderation/reports/${report.id}`, { headers: reporter.headers })).json()).resolution_status).toBe('pending')
  await page.screenshot({ path: info.outputPath('p7-compensated.png'), fullPage: true })
  await page.getByRole('button', { name: 'Reintentar decisión', exact: true }).click()
  await expect(page.getByText('Decisión completada', { exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(page).toHaveURL(new RegExp(`/moderacion/operaciones/${job.operation_id}$`))
  expect((await request.get(`/backend/api/v1/posts/${postId}`)).status()).toBe(404)
})
