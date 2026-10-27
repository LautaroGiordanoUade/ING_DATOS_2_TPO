import { randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

test.setTimeout(120_000)
test.use({ actionTimeout: 15_000 })
async function account(request: APIRequestContext, name: string) {
  const username = `qa_p7_ui_${randomUUID().slice(0, 12)}`
  const password = randomUUID()
  const created = await request.post('/backend/api/v1/users', { data: {
    username, password, full_name: name, email: `${username}@example.test`,
  } })
  expect(created.status()).toBe(201)
  const actor = await created.json() as { id: string }
  const login = await request.post('/backend/api/v1/users/login', { data: { username, password } })
  const token = await login.json() as { access_token: string }
  return { ...actor, username, password, name, headers: { Authorization: `Bearer ${token.access_token}` } }
}
function role(id: string, role: 'user' | 'moderator' | 'admin') {
  // Fixture setup only: a newly created QA identity, never existing users or seeds.
  execFileSync('docker', ['compose', 'exec', '-T', 'api', 'python', '-c', `
import asyncio, json, sys
from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
data = json.load(sys.stdin)
async def main():
    settings = get_settings()
    client = create_mongo_client(settings.mongodb_url)
    try:
        assert data['role'] in ('user', 'moderator', 'admin')
        result = await client[settings.mongodb_database].users.update_one(
            {'_id': data['id'], 'username': {'$regex': '^qa_p7_ui_'}}, {'$set': {'role': data['role']}})
        assert result.matched_count == 1
    finally:
        await client.close()
asyncio.run(main())
`], { cwd: fileURLToPath(new URL('../../../', import.meta.url)), input: JSON.stringify({ id, role }), windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] })
}
async function login(page: Page, actor: Awaited<ReturnType<typeof account>>, base?: string) {
  if (await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).isVisible()) await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  await page.goto(base ? new URL('/login', base).href : '/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(actor.username)
  await page.getByLabel('Contraseña', { exact: true }).fill(actor.password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Mi perfil', exact: true })).toHaveText(`@${actor.username}`)
  await page.getByRole('navigation').getByRole('link', { name: 'Inicio', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
}
async function publish(request: APIRequestContext, actor: Awaited<ReturnType<typeof account>>, text: string) {
  const response = await request.post('/backend/api/v1/posts', { headers: actor.headers,
    data: { user_id: actor.id, text, visibility: 'public', interests: ['datos'] } })
  expect(response.status()).toBe(202)
  const job = await response.json() as { operation_id: string; post_id: string }
  await expect.poll(async () => {
    const result = await request.get(`/backend/api/v1/problems/operations/${job.operation_id}`)
    return (await result.json() as { status: string }).status
  }, { timeout: 30_000 }).toBe('completed')
  return job.post_id
}

test('P7 reportar, ocultar varios reportes y revertir desde uno asociado preserva permisos e historial', async ({ page, request, browser }, info) => {
  const author = await account(request, 'Autor para moderación')
  const reporter = await account(request, 'Segundo reportante')
  const moderator = await account(request, 'Moderador P7')
  role(moderator.id, 'moderator')
  const text = 'Contenido revisable incluso después del ocultamiento'
  const postId = await publish(request, author, text)
  expect((await request.post('/backend/api/v1/problems/5/reaction', { headers: author.headers,
    data: { post_id: postId, user_id: author.id, kind: 'like' } })).status()).toBe(202)
  expect((await request.post('/backend/api/v1/problems/5/comment', { headers: { ...author.headers, 'Idempotency-Key': randomUUID() },
    data: { post_id: postId, user_id: author.id, text: 'Comentario preservado por moderación' } })).status()).toBe(202)
  await login(page, author)
  await page.getByRole('navigation').getByRole('link', { name: 'Mis publicaciones', exact: true }).click()
  await expect(page.getByText('1 reacciones · 1 comentarios', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Reportar publicación', exact: true }).click()
  await page.getByRole('combobox', { name: 'Motivo del reporte', exact: true }).selectOption('abuse')
  await page.getByLabel('Descripción del reporte (opcional)').fill('Revisar este contenido de prueba')
  await page.getByRole('button', { name: 'Enviar reporte', exact: true }).click()
  const receipt = page.getByRole('link', { name: 'Ver mi reporte', exact: true })
  await expect(receipt).toBeVisible()
  const reportPath = await receipt.getAttribute('href')
  await receipt.click()
  await expect(page.getByText('Tu reporte fue recibido y está pendiente de revisión.', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Moderación', exact: true })).toHaveCount(0)
  await page.goto('/moderacion')
  await expect(page.getByRole('heading', { name: 'Acceso restringido', exact: true })).toBeVisible()
  expect((await request.get(`/backend/api/v1/moderation/posts/${postId}/content`, { headers: author.headers })).status()).toBe(403)
  const second = await request.post('/backend/api/v1/moderation/reports', { headers: reporter.headers,
    data: { post_id: postId, reason: 'spam', description: 'Segundo reporte asociado' } })
  expect(second.status()).toBe(201)
  const associated = await second.json() as { id: string }
  const context = await browser.newContext({ viewport: page.viewportSize()!, locale: 'es-AR', timezoneId: 'America/Buenos_Aires' })
  const review = await context.newPage()
  try {
    await login(review, moderator, page.url())
    await review.getByRole('link', { name: 'Moderación', exact: true }).click()
    await review.locator(`a[href="${reportPath}"]`).click()
    const preview = review.getByRole('region', { name: 'Publicación en revisión', exact: true })
    await expect(preview.getByText(text, { exact: true })).toBeVisible()
    await review.getByRole('button', { name: 'Ocultar publicación', exact: true }).click()
    await review.getByLabel('Motivo de la decisión', { exact: true }).fill('Abuso confirmado por moderación')
    await review.getByRole('button', { name: 'Confirmar ocultamiento', exact: true }).click()
    await expect(preview.getByText('Estado de moderación: Oculta', { exact: true })).toBeVisible()
    await expect(review.getByText('2 reportes afectados', { exact: true })).toBeVisible()
    await expect(preview.getByText(text, { exact: true })).toBeVisible()
    expect((await request.get(`/backend/api/v1/posts/${postId}`)).status()).toBe(404)
    const hiddenState = await request.get(`/backend/api/v1/moderation/posts/${postId}/state`, { headers: moderator.headers })
    expect(Object.values((await hiddenState.json() as { counters: Record<string, number> }).counters)).toEqual([0, 0])
    expect(await review.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await review.screenshot({ path: info.outputPath('moderation-hidden.png'), fullPage: true })
    await review.reload()
    await expect(preview.getByText(text, { exact: true })).toBeVisible()
    await review.goto(new URL(`/reportes/${associated.id}`, review.url()).href)
    await review.getByRole('button', { name: 'Revertir ocultamiento', exact: true }).click()
    await review.getByLabel('Motivo de la decisión', { exact: true }).fill('Revisión: contenido permitido')
    await review.getByRole('button', { name: 'Confirmar reversión', exact: true }).click()
    await expect(preview.getByText('Estado de moderación: Pendiente de revisión', { exact: true })).toBeVisible()
    await expect(review.getByText('2 reportes afectados', { exact: true })).toHaveCount(2)
    const restored = await request.get(`/backend/api/v1/posts/${postId}`)
    expect(restored.status()).toBe(200)
    expect(await restored.json()).toMatchObject({ reaction_count: 1, comment_count: 1 })
    await review.screenshot({ path: info.outputPath('moderation-reverted.png'), fullPage: true })
    await page.goto(reportPath!)
    await expect(page.getByText('Revertido', { exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Publicación en revisión' })).toHaveCount(0)
    await page.getByRole('navigation').getByRole('link', { name: 'Mis publicaciones', exact: true }).click()
    await expect(page.getByText('1 reacciones · 1 comentarios', { exact: true })).toBeVisible()
    expect((await request.get(`/backend/api/v1/moderation/reports/${associated.id}`, { headers: author.headers })).status()).toBe(403)
  } finally { await context.close() }
})

test('P7 rechazo individual, duplicados y revocación de rol administrativo', async ({ page, request }, info) => {
  const author = await account(request, 'Reportante P7')
  const admin = await account(request, 'Administrador P7')
  role(admin.id, 'admin')
  const text = 'Publicación que permanece visible tras rechazar el reporte'
  const postId = await publish(request, author, text)
  const first = await request.post('/backend/api/v1/moderation/reports', { headers: author.headers, data: { post_id: postId, reason: 'other' } })
  expect(first.status()).toBe(201)
  const report = await first.json() as { id: string }
  await login(page, author)
  await page.getByRole('navigation').getByRole('link', { name: 'Mis publicaciones', exact: true }).click()
  await page.getByRole('button', { name: 'Reportar publicación', exact: true }).click()
  await page.getByRole('button', { name: 'Enviar reporte', exact: true }).click()
  await expect(page.getByText('Ya enviaste un reporte sobre esta publicación.', { exact: true })).toBeVisible()
  await login(page, admin)
  await page.getByRole('link', { name: 'Moderación', exact: true }).click()
  await page.locator(`a[href="/reportes/${report.id}"]`).click()
  await expect(page.getByText(text, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Rechazar reporte', exact: true }).click()
  await page.getByLabel('Motivo de la decisión', { exact: true }).fill('No se encontró una infracción')
  await page.getByRole('button', { name: 'Confirmar rechazo', exact: true }).click()
  await expect(page.getByText('Rechazado', { exact: true })).toBeVisible()
  await expect(page.getByText('1 reporte afectado', { exact: true })).toBeVisible()
  expect((await request.get(`/backend/api/v1/posts/${postId}`)).status()).toBe(200)
  await page.screenshot({ path: info.outputPath('moderation-rejected.png'), fullPage: true })
  role(admin.id, 'user')
  await page.getByRole('link', { name: '← Reportes', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Acceso restringido', exact: true })).toBeVisible()
  await expect(page.getByText(text, { exact: true })).toHaveCount(0)
})
