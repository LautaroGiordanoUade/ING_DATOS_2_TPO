import { randomUUID } from 'node:crypto'
import { test, expect, type Page } from '@playwright/test'

test.setTimeout(60_000)

test('P5 restaura reacción tras recarga y nueva sesión; cambio y baja permanecen guardados', async ({ page, request, browser }, info) => {
  const username = `qa_reaction_${randomUUID().replaceAll('-', '').slice(0, 16)}`
  const password = `Qa!${randomUUID()}`
  const registration = await request.post('/backend/api/v1/users', { data: {
    username, password, full_name: 'QA Reacción propia', email: `${username}@example.test`,
  } })
  expect(registration.status()).toBe(201)
  const user = await registration.json() as { id: string }
  const authResponse = await request.post('/backend/api/v1/users/login', { data: { username, password } })
  const auth = await authResponse.json() as { access_token: string }
  const headers = { Authorization: `Bearer ${auth.access_token}` }
  const publication = await request.post('/backend/api/v1/posts', { headers, data: {
    user_id: user.id, text: 'QA reacción persistida', interests: ['datos'], media: [], visibility: 'public',
  } })
  expect(publication.status()).toBe(202)
  const job = await publication.json() as { operation_id: string }
  await expect.poll(async () => {
    const operation = await request.get(`/backend/api/v1/problems/operations/${job.operation_id}`)
    return (await operation.json() as { status: string }).status
  }, { timeout: 30_000 }).toBe('completed')

  async function login(target: Page) {
    await target.goto('/login')
    await target.getByLabel('Nombre de usuario', { exact: true }).fill(username)
    await target.getByLabel('Contraseña', { exact: true }).fill(password)
    await target.getByRole('button', { name: 'Ingresar', exact: true }).click()
    await expect(target.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
    await target.goto('/mis-publicaciones')
  }

  await login(page)
  const like = page.getByRole('button', { name: '👍 Me gusta', exact: true })
  await expect(like).toBeEnabled()
  await like.click()
  await expect(page.getByText('1 reacciones · 0 comentarios', { exact: true })).toBeVisible()
  await page.reload()
  await expect(like).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('button', { name: 'Quitar mi reacción' })).toBeVisible()
  await page.getByRole('button', { name: '❤️ Me encanta', exact: true }).click()
  await expect(page.getByText('Reacción enviada (love).', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: '❤️ Me encanta', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.screenshot({ path: info.outputPath('reaction-restored.png'), fullPage: true })

  // A fresh browser context has no persisted sessionStorage or reaction cache.
  const fresh = await browser.newContext({
    baseURL: info.project.use.baseURL || 'http://127.0.0.1:4174',
    viewport: info.project.use.viewport ?? { width: 1440, height: 1000 },
    locale: 'es-AR', timezoneId: 'America/Buenos_Aires',
  })
  try {
    const second = await fresh.newPage()
    await login(second)
    await expect(second.getByRole('button', { name: '❤️ Me encanta', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await second.getByRole('button', { name: 'Quitar mi reacción', exact: true }).click()
    await expect(second.getByText('0 reacciones · 0 comentarios', { exact: true })).toBeVisible()
    await second.reload()
    await expect(second.getByRole('button', { name: '👍 Me gusta', exact: true })).toBeEnabled()
    await expect(second.getByRole('button', { name: 'Quitar mi reacción' })).toHaveCount(0)
    await expect(second.getByRole('button', { name: '❤️ Me encanta', exact: true })).toHaveAttribute('aria-pressed', 'false')
  } finally {
    await fresh.close()
  }
})
