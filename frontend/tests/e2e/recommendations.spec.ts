import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test.setTimeout(90_000)

test('P4 guarda intereses, cambia ranking y conserva preferencias al recargar', async ({ page, request }, info) => {
  const topic = `tema-${randomUUID().slice(0, 8)}`
  async function account(label: string, interests: string[] = []) {
    const username = `qa_p4_${label}_${randomUUID().slice(0, 8)}`
    const password = `Qa!${randomUUID()}`
    const created = await request.post('/backend/api/v1/users', { data: {
      username, password, interests, full_name: `QA ${label}`, email: `${username}@example.test`,
    } })
    expect(created.status()).toBe(201)
    const actor = await created.json() as { id: string }
    const login = await request.post('/backend/api/v1/users/login', { data: { username, password } })
    const auth = await login.json() as { access_token: string }
    return { ...actor, username, password, headers: { Authorization: `Bearer ${auth.access_token}` } }
  }
  const viewer = await account('viewer')
  const a = await account('bridgea'), b = await account('bridgeb')
  const popular = await account('popular')
  const relevant = await account('relevant', [topic])
  const fallback = await account('fallback', [topic])
  async function follow(from: typeof viewer, to: typeof viewer) {
    const response = await request.post('/backend/api/v1/social/follows', {
      headers: from.headers, data: { user_id: from.id, followed_user_id: to.id },
    })
    expect(response.status()).toBe(202)
    const job = await response.json() as { operation_id: string }
    await expect.poll(async () => {
      const operation = await request.get(`/backend/api/v1/social/operations/${job.operation_id}`, { headers: from.headers })
      return (await operation.json() as { status: string }).status
    }, { timeout: 30_000 }).toBe('completed')
  }
  await follow(viewer, a)
  await follow(viewer, b)
  await follow(a, popular)
  await follow(b, popular)
  await follow(a, relevant)
  await page.goto('/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(viewer.username)
  await page.getByLabel('Contraseña', { exact: true }).fill(viewer.password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
  await page.goto('/recomendaciones')
  const cards = page.locator('.user-grid article')
  await expect(cards).toHaveCount(2)
  await expect(cards.first()).toContainText('@' + popular.username)
  await page.getByLabel('Agregar interés').fill(topic.toUpperCase())
  await page.getByRole('button', { name: 'Guardar intereses', exact: true }).click()
  await expect(page.getByText('Intereses guardados.', { exact: true })).toBeVisible()
  await expect(cards).toHaveCount(3)
  await expect(cards.nth(0)).toContainText('@' + relevant.username)
  await expect(cards.nth(1)).toContainText('@' + popular.username)
  await expect(cards.nth(2)).toContainText('@' + fallback.username)
  await expect(cards.first().getByLabel('Intereses compartidos')).toContainText('#' + topic)
  await page.reload()
  await expect(page.getByRole('button', { name: `Quitar ${topic}`, exact: true })).toBeVisible()
  await expect(cards.first()).toContainText('@' + relevant.username)
  const field = await page.getByLabel('Agregar interés').boundingBox()
  expect(field?.height).toBeLessThan(70)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: info.outputPath('p4-interests.png'), fullPage: true })
  await page.getByRole('button', { name: `Quitar ${topic}`, exact: true }).click()
  await page.getByRole('button', { name: 'Guardar intereses', exact: true }).click()
  await expect(cards).toHaveCount(2)
  await expect(cards.first()).toContainText('@' + popular.username)
  await page.reload()
  await expect(page.getByRole('button', { name: `Quitar ${topic}`, exact: true })).toHaveCount(0)
})
