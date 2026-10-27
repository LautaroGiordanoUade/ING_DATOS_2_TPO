import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test.setTimeout(90_000)

test('P5 muestra comentarios paginados, agrega el nuevo sin duplicar y lo conserva al recargar', async ({ page, request }, info) => {
  const username = `qa_comments_${randomUUID().slice(0, 12)}`
  const password = `Qa!${randomUUID()}`
  const registration = await request.post('/backend/api/v1/users', { data: {
    username, password, full_name: 'QA Comentarios', email: `${username}@example.test`,
  } })
  expect(registration.status()).toBe(201)
  const user = await registration.json() as { id: string }
  const login = await request.post('/backend/api/v1/users/login', { data: { username, password } })
  const auth = await login.json() as { access_token: string }
  const headers = { Authorization: `Bearer ${auth.access_token}` }
  const publication = await request.post('/backend/api/v1/posts', { headers, data: {
    user_id: user.id, text: 'Post para comentarios visibles', interests: ['datos'], visibility: 'public',
  } })
  expect(publication.status()).toBe(202)
  const job = await publication.json() as { operation_id: string; post_id: string }
  await expect.poll(async () => {
    const operation = await request.get(`/backend/api/v1/problems/operations/${job.operation_id}`)
    return (await operation.json() as { status: string }).status
  }, { timeout: 30_000 }).toBe('completed')
  const keys = Array.from({ length: 12 }, () => randomUUID())
  for (let index = 0; index < 12; index++) {
    const comment = await request.post('/backend/api/v1/problems/5/comment', {
      headers: { ...headers, 'Idempotency-Key': keys[index]! },
      data: { post_id: job.post_id, user_id: user.id, text: `Comentario previo ${index}` },
    })
    expect(comment.status()).toBe(202)
  }
  const replay = await request.post('/backend/api/v1/problems/5/comment', {
    headers: { ...headers, 'Idempotency-Key': keys[11]! },
    data: { post_id: job.post_id, user_id: user.id, text: 'Comentario previo 11' },
  })
  expect(replay.status()).toBe(202)
  await page.goto('/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(username)
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Tu feed', exact: true })).toBeVisible()
  await page.goto('/mis-publicaciones')
  const list = page.getByRole('region', { name: 'Comentarios de la publicación' })
  await expect(list.locator('.comment-item')).toHaveCount(10)
  await list.getByRole('button', { name: 'Cargar comentarios anteriores' }).click()
  await expect(list.locator('.comment-item')).toHaveCount(12)
  await page.getByRole('button', { name: '💬 Escribir comentario', exact: true }).click()
  await page.getByLabel('Escribí un comentario', { exact: true }).fill('Este comentario ahora se ve debajo')
  await page.getByRole('button', { name: 'Comentar', exact: true }).click()
  await expect(list.getByText('Este comentario ahora se ve debajo', { exact: true })).toBeVisible()
  await expect(list.locator('.comment-item')).toHaveCount(10)
  await expect(page.getByText('0 reacciones · 13 comentarios', { exact: true })).toBeVisible()
  await page.reload()
  await expect(list.getByText('Este comentario ahora se ve debajo', { exact: true })).toBeVisible()
  await expect(list.locator('.comment-item').first()).toContainText('QA Comentarios')
  await expect(list.locator('.comment-item').first().locator('time')).toHaveAttribute('datetime', /Z$/)
  const publishedAt = await page.locator('article.post-card > .author-line time').getAttribute('datetime')
  const commentedAt = await list.locator('.comment-item').first().locator('time').getAttribute('datetime')
  expect(Date.parse(commentedAt!)).toBeGreaterThanOrEqual(Date.parse(publishedAt!))
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.screenshot({ path: info.outputPath('comments-after-reload.png'), fullPage: true })
  await list.getByRole('button', { name: 'Cargar comentarios anteriores' }).click()
  await expect(list.locator('.comment-item')).toHaveCount(13)
  const texts = await list.locator('.comment-item p').allTextContents()
  expect(new Set(texts).size).toBe(13)
})
