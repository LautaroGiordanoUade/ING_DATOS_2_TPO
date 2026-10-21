import { randomUUID } from 'node:crypto'
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { z } from 'zod'

test.setTimeout(60_000)
const profileSchema = z.object({ id: z.uuid() })
const acceptedSchema = z.object({ operation_id: z.uuid(), post_id: z.uuid(), status: z.string() })
const credentials = () => ({ username: `qa_p1_${randomUUID().replaceAll('-', '').slice(0, 20)}`, password: `Qa!${randomUUID()}` })
async function account(request: APIRequestContext) {
  const values = credentials()
  const response = await request.post('/backend/api/v1/users', { data: { ...values, full_name: 'QA Comunidad', email: `${values.username}@example.test`, account_type: 'public' } })
  expect(response.status()).toBe(201)
  return { ...values, id: profileSchema.parse(await response.json()).id }
}
async function bearer(request: APIRequestContext, values: { username: string; password: string }) {
  const response = await request.post('/backend/api/v1/users/login', { data: values })
  expect(response.ok()).toBeTruthy()
  return z.object({ access_token: z.string() }).parse(await response.json()).access_token
}
async function loginUi(page: Page, values: { username: string; password: string }) {
  await page.goto('/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(values.username)
  await page.getByLabel('Contraseña', { exact: true }).fill(values.password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Mis publicaciones', exact: true })).toBeVisible()
}

test('P1 registro, sesión, publicación, distribución real, recarga y logout', async ({ page, request }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  const values = credentials()
  await page.goto('/registro')
  await expect(page.getByRole('heading', { name: 'Creá tu cuenta' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('p1-register.png'), fullPage: true })
  await page.getByLabel('Nombre completo').fill('QA Comunidad')
  await page.getByLabel('Nombre de usuario').fill(values.username)
  await page.getByLabel('Email', { exact: true }).fill(`${values.username}@example.test`)
  await page.getByLabel('Contraseña', { exact: true }).fill(values.password)
  await page.getByRole('button', { name: 'Crear cuenta', exact: true }).click()
  await expect(page.getByText('Tu cuenta está creada. Iniciá sesión para publicar.')).toBeVisible()
  await page.screenshot({ path: info.outputPath('p1-login.png'), fullPage: true })
  await page.getByLabel('Contraseña', { exact: true }).fill(values.password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Mis publicaciones', exact: true })).toBeVisible()
  await expect(page.getByText('Todavía no publicaste.')).toBeVisible()
  await page.screenshot({ path: info.outputPath('p1-empty.png'), fullPage: true })
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Mis publicaciones', exact: true })).toBeVisible()

  // P2 is used only to set up a real follower; no follow UI is part of this iteration.
  const token = await bearer(request, values)
  const me = profileSchema.parse(await (await request.get('/backend/api/v1/users/me', { headers: { Authorization: `Bearer ${token}` } })).json())
  const follower = await account(request)
  const minimalPost = { user_id: me.id, text: 'Rechazado sin identidad', interests: ['datos'], media: [], visibility: 'public' }
  expect((await request.post('/backend/api/v1/posts', { data: minimalPost })).status()).toBe(401)
  expect((await request.post('/backend/api/v1/posts', { headers: { Authorization: `Bearer ${token}` }, data: { ...minimalPost, user_id: follower.id } })).status()).toBe(403)
  const followerToken = await bearer(request, follower)
  const follow = await request.post('/backend/api/v1/social/follows', { headers: { Authorization: `Bearer ${followerToken}` }, data: { user_id: follower.id, followed_user_id: me.id } })
  expect(follow.status()).toBe(202)
  const followId = z.object({ operation_id: z.uuid() }).parse(await follow.json()).operation_id
  await expect.poll(async () => {
    const response = await request.get(`/backend/api/v1/social/operations/${followId}`, { headers: { Authorization: `Bearer ${followerToken}` } })
    return z.object({ status: z.string() }).parse(await response.json()).status
  }, { timeout: 20_000 }).toBe('completed')

  await page.getByRole('link', { name: 'Publicar', exact: true }).click()
  const text = `Una idea sobre datos · ${values.username}`
  await page.getByLabel('Tu publicación').fill(text)
  await page.getByLabel('Intereses', { exact: true }).fill('datos, python')
  await page.reload()
  await expect(page.getByLabel('Tu publicación')).toHaveValue(text)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: info.outputPath('p1-composer.png'), fullPage: true })
  const accepted = page.waitForResponse((response) => response.url().endsWith('/api/v1/posts') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Publicar', exact: true }).click()
  const response = await accepted
  expect(response.status()).toBe(202)
  const job = acceptedSchema.parse(await response.json())
  await expect(page).toHaveURL(new RegExp(`/operaciones/${job.operation_id}$`))
  await expect(page.getByText('Tu idea ya está publicada.')).toBeVisible({ timeout: 25_000 })
  await expect(page.getByText(text, { exact: true })).toBeVisible()
  const detail = await request.get(`/backend/api/v1/problems/operations/${job.operation_id}`)
  expect(z.object({ post_id: z.uuid() }).parse(await detail.json()).post_id).toBe(job.post_id)
  await page.getByLabel('UUID de la cuenta destinataria').fill(follower.id)
  await page.getByRole('button', { name: 'Comprobar', exact: true }).click()
  await expect(page.getByText('La publicación está visible para esta cuenta.')).toBeVisible()
  await page.evaluate(() => scrollTo(0, 0))
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: info.outputPath('p1-published.png'), fullPage: true })
  await page.reload()
  await expect(page.getByText(text, { exact: true })).toBeVisible()
  await page.getByRole('link', { name: /Mis publicaciones/ }).click()
  await expect(page.getByText(text, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Lo que te interesa')
  expect(await page.evaluate(() => sessionStorage.getItem('niche.session.token'))).toBeNull()
  await page.goto('/publicar')
  await expect(page).toHaveURL(/\/login$/)
  expect(errors).toEqual([])
})

test('P1 replay idempotente y compensación real se muestran sin falso éxito', async ({ page, request }, info) => {
  const actor = await account(request)
  await loginUi(page, actor)
  const headers = { 'Idempotency-Key': randomUUID(), 'X-Fail-At-Step': 'mongo_create_post' }
  const data = { user_id: actor.id, text: 'Prueba aislada de compensación P1', interests: ['datos'], media: [], visibility: 'public' }
  const response = await request.post('/backend/api/v1/problems/1/publish', { headers, data })
  expect(response.status()).toBe(202)
  const job = acceptedSchema.parse(await response.json())
  const replay = await request.post('/backend/api/v1/problems/1/publish', { headers, data })
  expect(acceptedSchema.parse(await replay.json()).operation_id).toBe(job.operation_id)
  const conflict = await request.post('/backend/api/v1/problems/1/publish', { headers, data: { ...data, text: 'Otro contenido' } })
  expect(conflict.status()).toBe(409)
  await page.goto(`/operaciones/${job.operation_id}`)
  await expect(page.getByText('Publicación cancelada', { exact: true })).toBeVisible({ timeout: 25_000 })
  await expect(page.getByText('Tu idea ya está publicada.')).toHaveCount(0)
  expect((await request.get(`/backend/api/v1/posts/${job.post_id}`)).status()).toBe(404)
  await page.screenshot({ path: info.outputPath('p1-compensated.png'), fullPage: true })
})

test('P1 credenciales incorrectas muestran error de login real', async ({ page, request }) => {
  const actor = await account(request)
  await page.goto('/login')
  await page.getByLabel('Nombre de usuario').fill(actor.username)
  await page.getByLabel('Contraseña', { exact: true }).fill('incorrecta')
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('No pudimos iniciar sesión')
  await expect(page.getByLabel('Nombre de usuario')).toHaveValue(actor.username)
})

test('P1 restaura una ruta protegida solo con credencial validada', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('niche.session.token', 'invalid-credential'))
  await page.goto('/publicar')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'Iniciá sesión' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('niche.session.token'))).toBeNull()
})
