import { randomUUID } from 'node:crypto'
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { z } from 'zod'
import { feedSchema } from '../../src/features/feed/api'

test.setTimeout(90_000)
const acceptedSchema = z.object({ operation_id: z.uuid(), post_id: z.uuid() })
async function account(request: APIRequestContext, accountType = 'public') {
  const username = `qa_p3_${randomUUID().replaceAll('-', '').slice(0, 18)}`
  const password = `Qa!${randomUUID()}`
  const response = await request.post('/backend/api/v1/users', { data: { username, password, full_name: `Comunidad ${username}`, email: `${username}@example.test`, account_type: accountType } })
  expect(response.status()).toBe(201)
  const id = z.object({ id: z.uuid() }).parse(await response.json()).id
  const login = await request.post('/backend/api/v1/users/login', { data: { username, password } })
  const token = z.object({ access_token: z.string() }).parse(await login.json()).access_token
  return { username, password, id, headers: { Authorization: `Bearer ${token}` } }
}
async function waitJob(request: APIRequestContext, path: string, headers: Record<string, string>) {
  await expect.poll(async () => {
    const response = await request.get(`/backend/api/v1/${path}`, { headers })
    return z.object({ status: z.string() }).parse(await response.json()).status
  }, { timeout: 30_000 }).toBe('completed')
}
async function follow(request: APIRequestContext, reader: Awaited<ReturnType<typeof account>>, author: Awaited<ReturnType<typeof account>>) {
  const response = await request.post('/backend/api/v1/social/follows', { headers: reader.headers, data: { user_id: reader.id, followed_user_id: author.id } })
  expect(response.status()).toBe(202)
  const id = z.object({ operation_id: z.uuid() }).parse(await response.json()).operation_id
  await waitJob(request, `social/operations/${id}`, reader.headers)
}
async function publish(request: APIRequestContext, author: Awaited<ReturnType<typeof account>>, text: string) {
  const response = await request.post('/backend/api/v1/posts', { headers: { ...author.headers, 'Idempotency-Key': randomUUID() }, data: { user_id: author.id, text, interests: ['datos'], media: [], visibility: 'public' } })
  expect(response.status()).toBe(202)
  return acceptedSchema.parse(await response.json())
}
async function login(page: Page, reader: Awaited<ReturnType<typeof account>>) {
  await page.goto('/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(reader.username)
  await page.getByLabel('Contraseña', { exact: true }).fill(reader.password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
}

test('P3 feed real 20/20/5, autores, contadores, refresco y unfollow', async ({ page, request }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  const author = await account(request)
  const reader = await account(request)
  const stranger = await account(request)
  await follow(request, reader, author)
  const jobs: Array<z.infer<typeof acceptedSchema>> = []
  for (let i = 1; i <= 45; i++) jobs.push(await publish(request, author, `Idea ${i} de ${author.username}`))
  await expect.poll(async () => {
    const states = await Promise.all(jobs.map(async (job) => z.object({ status: z.string() }).parse(await (await request.get(`/backend/api/v1/problems/operations/${job.operation_id}`)).json()).status))
    return states.every((state) => state === 'completed')
  }, { timeout: 30_000 }).toBe(true)
  const excludedText = `Publicación no seguida ${stranger.username}`
  const excluded = await publish(request, stranger, excludedText)
  await waitJob(request, `problems/operations/${excluded.operation_id}`, stranger.headers)

  expect((await request.get(`/backend/api/v1/feeds/${author.id}`, { headers: reader.headers })).status()).toBe(403)
  const initial = page.waitForResponse((response) => response.url().endsWith(`/api/v1/feeds/${reader.id}`))
  await login(page, reader)
  const first = feedSchema.parse(await (await initial).json())
  expect(first.items).toHaveLength(20)
  await expect(page.getByRole('article')).toHaveCount(20)
  await expect(page.getByText(`@${author.username}`, { exact: true })).toHaveCount(20)
  await expect(page.getByText(excludedText, { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: info.outputPath('feed.png') })

  await page.getByRole('button', { name: 'Cargar más publicaciones' }).click()
  await expect(page.getByRole('article')).toHaveCount(40)
  await page.getByRole('button', { name: 'Cargar más publicaciones' }).click()
  await expect(page.getByRole('article')).toHaveCount(45)
  await expect(page.getByRole('button', { name: 'Cargar más publicaciones' })).toHaveCount(0)
  await expect(page.getByText(excludedText, { exact: true })).toHaveCount(0)

  const target = first.items[0]!
  const reaction = await request.post('/backend/api/v1/problems/5/reaction', { data: { post_id: target.id, user_id: reader.id, kind: 'like' } })
  expect(reaction.status()).toBe(202)
  const freshText = `Nueva idea ${randomUUID()}`
  const fresh = await publish(request, author, freshText)
  await waitJob(request, `problems/operations/${fresh.operation_id}`, author.headers)
  await page.getByRole('button', { name: 'Actualizar feed' }).click()
  await expect(page.getByRole('article')).toHaveCount(20)
  await expect(page.getByText(freshText, { exact: true })).toBeVisible()
  await expect(page.getByRole('article').filter({ hasText: target.text }).getByText('1 reacciones · 0 comentarios')).toBeVisible()
  await page.getByRole('navigation').getByRole('link', { name: 'Mis publicaciones', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Mis publicaciones', exact: true })).toBeVisible()
  await expect(page.getByText('Todavía no publicaste.')).toBeVisible()
  await page.getByRole('navigation').getByRole('link', { name: 'Inicio', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()

  const unfollow = await request.delete('/backend/api/v1/social/follows', { headers: reader.headers, data: { user_id: reader.id, followed_user_id: author.id } })
  expect(unfollow.status()).toBe(202)
  const id = z.object({ operation_id: z.uuid() }).parse(await unfollow.json()).operation_id
  await waitJob(request, `social/operations/${id}`, reader.headers)
  await expect(page.getByRole('button', { name: 'Actualizar feed' })).toBeEnabled()
  await page.getByRole('button', { name: 'Actualizar feed' }).click()
  await expect(page.getByText('Tu feed todavía está vacío.')).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('feed-empty.png') })
  expect(errors).toEqual([])
})

test('P3 una solicitud privada pendiente no habilita posts; la aprobación real sí', async ({ page, request }) => {
  const author = await account(request, 'private')
  const reader = await account(request)
  const text = `Idea pública de cuenta privada ${author.username}`
  const post = await publish(request, author, text)
  await waitJob(request, `problems/operations/${post.operation_id}`, author.headers)
  await follow(request, reader, author)
  await login(page, reader)
  await expect(page.getByText('Tu feed todavía está vacío.')).toBeVisible()
  const approval = await request.post('/backend/api/v1/social/follows/approve', { headers: author.headers, data: { user_id: reader.id, followed_user_id: author.id } })
  expect(approval.status()).toBe(202)
  const id = z.object({ operation_id: z.uuid() }).parse(await approval.json()).operation_id
  await waitJob(request, `social/operations/${id}`, author.headers)
  await page.getByRole('button', { name: 'Actualizar feed' }).click()
  await expect(page.getByText(text, { exact: true })).toBeVisible()
})
