import { randomUUID } from 'node:crypto'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

test.setTimeout(120_000)
async function account(request: APIRequestContext, fullName: string, accountType = 'public') {
  const username = `qa_p2_${randomUUID().slice(0, 12)}`
  const password = `Qa!${randomUUID()}`
  const response = await request.post('/backend/api/v1/users', { data: { username, password,
    full_name: fullName, email: `${username}@example.test`, account_type: accountType } })
  expect(response.status()).toBe(201)
  const actor = await response.json() as { id: string }
  const login = await request.post('/backend/api/v1/users/login', { data: { username, password } })
  const token = await login.json() as { access_token: string }
  return { ...actor, username, password, fullName, headers: { Authorization: `Bearer ${token.access_token}` } }
}
async function login(page: Page, actor: Awaited<ReturnType<typeof account>>, base?: string) {
  await page.goto(base ? new URL('/login', base).href : '/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(actor.username)
  await page.getByLabel('Contraseña', { exact: true }).fill(actor.password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
}
async function publish(request: APIRequestContext, actor: Awaited<ReturnType<typeof account>>, text: string) {
  const response = await request.post('/backend/api/v1/posts', { headers: actor.headers,
    data: { user_id: actor.id, text, visibility: 'public', interests: ['datos'] } })
  expect(response.status()).toBe(202)
  const job = await response.json() as { operation_id: string }
  await expect.poll(async () => {
    const status = await request.get(`/backend/api/v1/problems/operations/${job.operation_id}`)
    return (await status.json() as { status: string }).status
  }, { timeout: 30_000 }).toBe('completed')
}
async function counter(page: Page, name: string, count: number) {
  await expect(page.locator('.follow-counts > div').filter({ has: page.locator('dt', { hasText: new RegExp(`^${name}$`) }) }).locator('dd')).toHaveText(String(count))
}

test('P2 seguir desde sugerencias, recargar, abrir el autor y dejar de seguir actualiza perfil y feed', async ({ page, request }, info) => {
  const author = await account(request, 'Autor público P2')
  const reader = await account(request, 'Lector público P2')
  const interest = `p2_${randomUUID().slice(0, 12)}`
  for (const actor of [author, reader]) {
    expect((await request.put('/backend/api/v1/users/me/interests', { headers: actor.headers, data: { interests: [interest] } })).status()).toBe(200)
  }
  await publish(request, author, 'Publicación para seguir desde el perfil')
  let follows = 0
  page.on('request', (req) => { if (req.method() === 'POST' && req.url().endsWith('/api/v1/social/follows')) follows++ })
  await login(page, reader)
  await page.getByRole('link', { name: 'Sugerencias', exact: true }).click()
  await page.getByRole('article', { name: `Perfil de ${author.fullName}`, exact: true }).getByRole('link', { name: 'Ver perfil', exact: true }).click()
  await expect(page.getByRole('heading', { name: author.fullName, exact: true })).toBeVisible()
  await counter(page, 'Seguidores', 0)
  await page.getByRole('button', { name: 'Seguir', exact: true }).click()
  await expect(page.getByText('Siguiendo', { exact: true })).toBeVisible()
  await counter(page, 'Seguidores', 1)
  await page.reload()
  await expect(page.getByText('Siguiendo', { exact: true })).toBeVisible()
  expect(follows).toBe(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: info.outputPath('public-profile.png'), fullPage: true })
  await page.getByRole('link', { name: 'Inicio', exact: true }).click()
  await expect(page.getByText('Publicación para seguir desde el perfil', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: author.fullName, exact: true }).click()
  await page.getByRole('button', { name: 'Dejar de seguir', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Seguir', exact: true })).toBeEnabled()
  await counter(page, 'Seguidores', 0)
  await page.getByRole('link', { name: 'Mi perfil', exact: true }).click()
  await expect(page.getByRole('heading', { name: reader.fullName, exact: true })).toBeVisible()
  await counter(page, 'Seguidos', 0)
  await expect(page.getByRole('button', { name: 'Seguir', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: 'Inicio', exact: true }).click()
  await expect(page.getByText('Tu feed todavía está vacío.', { exact: true })).toBeVisible()
})

test('P2 solicitud privada, cancelación y aprobación desde otra sesión conservan el estado real', async ({ page, request, browser }, info) => {
  const owner = await account(request, 'Cuenta privada P2', 'private')
  const reader = await account(request, 'Solicitante P2')
  await publish(request, owner, 'Contenido de la cuenta privada P2')
  await login(page, reader)
  await page.goto(`/perfiles/${owner.id}`)
  await page.getByRole('button', { name: 'Seguir', exact: true }).click()
  await expect(page.getByText('Solicitud enviada', { exact: true })).toBeVisible()
  await counter(page, 'Seguidores', 0)
  await page.getByRole('button', { name: 'Cancelar solicitud', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Seguir', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Seguir', exact: true }).click()
  await expect(page.getByText('Solicitud enviada', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('Solicitud enviada', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Inicio', exact: true }).click()
  await expect(page.getByText('Tu feed todavía está vacío.', { exact: true })).toBeVisible()
  const context = await browser.newContext({ viewport: page.viewportSize()!, locale: 'es-AR', timezoneId: 'America/Buenos_Aires' })
  const other = await context.newPage()
  try {
    await login(other, owner, page.url())
    await other.getByRole('link', { name: 'Solicitudes', exact: true }).click()
    const card = other.getByRole('listitem', { name: `Solicitud de ${reader.fullName}`, exact: true })
    await expect(card).toBeVisible()
    await card.getByRole('link', { name: reader.fullName, exact: true }).click()
    await expect(other.getByRole('heading', { name: reader.fullName, exact: true })).toBeVisible()
    await other.getByRole('link', { name: 'Solicitudes', exact: true }).click()
    expect(await other.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await other.screenshot({ path: info.outputPath('private-requests.png'), fullPage: true })
    await other.getByRole('button', { name: 'Aprobar solicitud', exact: true }).click()
    await expect(other.getByText('No tenés solicitudes pendientes.', { exact: true })).toBeVisible()
    await other.getByRole('link', { name: 'Mi perfil', exact: true }).click()
    await counter(other, 'Seguidores', 1)
    await page.goto(`/perfiles/${owner.id}`)
    await expect(page.getByText('Siguiendo', { exact: true })).toBeVisible()
    await counter(page, 'Seguidores', 1)
    await page.getByRole('link', { name: 'Inicio', exact: true }).click()
    await expect(page.getByText('Contenido de la cuenta privada P2', { exact: true })).toBeVisible()
    await page.getByRole('link', { name: owner.fullName, exact: true }).click()
    await page.getByRole('button', { name: 'Dejar de seguir', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Seguir', exact: true })).toBeEnabled()
  } finally { await context.close() }
})
