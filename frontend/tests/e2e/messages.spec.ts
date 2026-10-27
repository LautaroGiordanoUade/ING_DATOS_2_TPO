import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test.setTimeout(120_000)

test('P6 crea un grupo, conserva historial paginado y coordina dos participantes', async ({ page, request, browser }, info) => {
  const password = `Qa!${randomUUID()}`
  const users = []
  for (const name of ['Emisor', 'Receptor']) {
    const username = `qa_p6_${randomUUID().slice(0, 12)}`
    const registration = await request.post('/backend/api/v1/users', { data: {
      username, password, full_name: `QA ${name}`, email: `${username}@example.test`,
    } })
    expect(registration.status()).toBe(201)
    const account = await registration.json() as { id: string }
    const login = await request.post('/backend/api/v1/users/login', { data: { username, password } })
    const token = await login.json() as { access_token: string }
    users.push({ ...account, username, headers: { Authorization: `Bearer ${token.access_token}` } })
  }
  const sender = users[0]!
  const receiver = users[1]!
  await page.goto('/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(sender.username)
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Mensajes', exact: true }).click()
  await page.getByRole('button', { name: 'Nuevo grupo', exact: true }).click()
  await page.getByLabel('Nombre del grupo', { exact: true }).fill('Comunidad P6')
  await page.getByLabel('Buscar participantes por usuario').fill(receiver.username)
  await page.getByRole('button', { name: `Agregar @${receiver.username} · QA Receptor`, exact: true }).click()
  await page.getByRole('button', { name: 'Crear grupo', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Comunidad P6', exact: true })).toBeVisible()
  const groupId = page.url().split('/').at(-1)!
  await page.getByLabel('Mensaje', { exact: true }).fill('Hola desde la interfaz')
  await page.getByRole('button', { name: 'Enviar mensaje', exact: true }).click()
  await expect(page.getByText('Hola desde la interfaz', { exact: true })).toBeVisible()
  for (let i = 0; i < 30; i++) {
    const response = await request.post(`/backend/api/v1/messages/conversations/${groupId}/messages`, {
      headers: { ...sender.headers, 'Idempotency-Key': randomUUID() }, data: { text: `Mensaje anterior ${i}` },
    })
    expect(response.status()).toBe(202)
  }
  const context = await browser.newContext({ viewport: page.viewportSize()! })
  const other = await context.newPage()
  try {
    await other.goto(new URL('/login', page.url()).href)
    await other.getByLabel('Nombre de usuario', { exact: true }).fill(receiver.username)
    await other.getByLabel('Contraseña', { exact: true }).fill(password)
    await other.getByRole('button', { name: 'Ingresar', exact: true }).click()
    await expect(other.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
    await other.getByRole('link', { name: 'Mensajes', exact: true }).click()
    await expect(other.getByRole('link', { name: 'Comunidad P6 31 sin leer', exact: true })).toBeVisible()
    await other.getByRole('link', { name: 'Comunidad P6 31 sin leer', exact: true }).click()
    await expect(other.locator('.chat-message')).toHaveCount(30)
    await other.getByRole('button', { name: 'Cargar mensajes anteriores', exact: true }).click()
    await expect(other.locator('.chat-message')).toHaveCount(31)
    await expect(other.getByText('Hola desde la interfaz', { exact: true })).toBeVisible()
    await other.getByRole('button', { name: 'Marcar hasta el último como leído' }).click()
    await expect.poll(async () => {
      const response = await request.get(`/backend/api/v1/messages/conversations/${groupId}`, { headers: receiver.headers })
      return (await response.json() as { unread: number }).unread
    }).toBe(0)
    await other.getByLabel('Mensaje', { exact: true }).fill('Respuesta del receptor')
    await other.getByRole('button', { name: 'Enviar mensaje', exact: true }).click()
    await expect(page.getByText('Respuesta del receptor', { exact: true })).toBeVisible({ timeout: 15_000 })
    await other.reload()
    await expect(other.getByText('Respuesta del receptor', { exact: true })).toBeVisible()
    expect(await other.getByRole('list', { name: 'Historial de mensajes' }).evaluate((element) => element.scrollHeight > element.clientHeight)).toBeTruthy()
    expect(await other.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    await other.screenshot({ path: info.outputPath('messages.png'), fullPage: true })
  } finally { await context.close() }
})
