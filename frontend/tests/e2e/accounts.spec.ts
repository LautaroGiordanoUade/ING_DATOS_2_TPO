import { randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { z } from 'zod'
import { accountJobSchema, traceSchema } from '../../src/features/accounts/contracts'
import { postSchema } from '../../src/features/posts/contracts'

test.setTimeout(120_000)
const root = fileURLToPath(new URL('../../../', import.meta.url))
let created: Array<{ id: string; username: string }> = []
const python = (code: string, args: string[] = []) => execFileSync('docker', ['compose', 'exec', '-T', 'api', 'python', '-c', code, ...args], { cwd: root, timeout: 40_000, encoding: 'utf8' })
test.beforeEach(() => { created = [] })
test.afterEach(() => {
  if (!created.length) return
  // Remove only this test's random fixtures. Never reset fixed P7/P8 or human accounts.
  python(`import asyncio,json,re,sys
from pymongo import AsyncMongoClient
from redis.asyncio import Redis
from neo4j import AsyncGraphDatabase
from app.core.config import get_settings
async def main():
 s=get_settings(); assert s.app_env=='development'
 mongo=AsyncMongoClient(s.mongodb_url); db=mongo[s.mongodb_database]
 redis=Redis.from_url(s.redis_url)
 graph=AsyncGraphDatabase.driver(s.neo4j_uri,auth=(s.neo4j_user,s.neo4j_password.get_secret_value()))
 try:
  actors=json.loads(sys.argv[1]); ids=[a['id'] for a in actors]
  for a in actors:
   assert re.fullmatch(r'qa_p8_[a-f0-9]{20}',a['username'])
   assert await db.users.find_one({'_id':a['id'],'username':a['username']})
  posts=[p['_id'] async for p in db.posts.find({'user_id':{'$in':ids}},{'_id':1})]
  reports=[r['_id'] async for r in db.moderation_reports.find({'post_id':{'$in':posts}},{'_id':1})]
  for _ in range(40):
   active=await db.account_jobs.count_documents({'user_id':{'$in':ids},'active':True})+await db.moderation_jobs.count_documents({'report_id':{'$in':reports},'active':True})
   if not active: break
   await asyncio.sleep(0.5)
  assert not active,'QA cleanup retained active recovery jobs'
  jobs=[j['_id'] async for j in db.account_jobs.find({'user_id':{'$in':ids}},{'_id':1})]
  for name in ('account_jobs','account_history'):
   await db[name].delete_many({'user_id':{'$in':ids}})
  await db.account_post_snapshots.delete_many({'operation_id':{'$in':jobs}})
  for name in ('moderation_jobs','moderation_history'):
   await db[name].delete_many({'report_id':{'$in':reports}})
  await db.moderation_reports.delete_many({'_id':{'$in':reports}})
  for name in ('reactions','comments'):
   await db[name].delete_many({'post_id':{'$in':posts}})
  await db.publication_jobs.delete_many({'post.user_id':{'$in':ids}})
  await db.posts.delete_many({'_id':{'$in':posts}})
  await db.conversations.delete_many({'participant_ids':{'$in':ids}})
  async with graph.session() as session:
   result=await session.run('MATCH (u:User) WHERE u.id IN $ids DETACH DELETE u',ids=ids)
   await result.consume()
  for identifier in ids+posts+jobs:
   keys=[key async for key in redis.scan_iter(match='*'+identifier+'*')]
   if keys: await redis.delete(*keys)
  await db.users.delete_many({'_id':{'$in':ids}})
 finally:
  await mongo.close(); await redis.aclose(); await graph.close()
asyncio.run(main())`, [JSON.stringify(created)])
})
async function account(request: APIRequestContext, role: 'user' | 'admin' = 'user') {
  const username = `qa_p8_${randomUUID().replaceAll('-', '').slice(0, 20)}`
  const password = `Qa!${randomUUID()}`
  const response = await request.post('/backend/api/v1/users', { data: { username, password, full_name: `QA Cuenta ${role}`, email: `${username}@example.test`, account_type: 'public' } })
  expect(response.status()).toBe(201)
  const id = z.object({ id: z.guid() }).parse(await response.json()).id
  created.push({ id, username })
  if (role === 'admin') python(`import asyncio,sys,json
from pymongo import AsyncMongoClient
from app.core.config import get_settings
async def main():
 s=get_settings(); assert s.app_env=='development'; c=AsyncMongoClient(s.mongodb_url)
 try:
  a=json.loads(sys.argv[1]); r=await c[s.mongodb_database].users.update_one({'_id':a['id'],'username':a['username'],'role':'user'},{'$set':{'role':'admin'}}); assert r.modified_count==1
 finally: await c.close()
asyncio.run(main())`, [JSON.stringify({ id, username })])
  const login = await request.post('/backend/api/v1/users/login', { data: { username, password } })
  expect(login.status()).toBe(200)
  const token = z.object({ access_token: z.string() }).parse(await login.json()).access_token
  return { username, password, id, headers: { Authorization: `Bearer ${token}` } }
}
type Actor = Awaited<ReturnType<typeof account>>
async function login(page: Page, actor: Actor) {
  await page.goto('/login')
  await page.getByLabel('Nombre de usuario', { exact: true }).fill(actor.username)
  await page.getByLabel('Contraseña', { exact: true }).fill(actor.password)
  await page.getByRole('button', { name: 'Ingresar', exact: true }).click()
  await expect(page.locator('.session-name')).toHaveText(`@${actor.username}`)
}
async function wait(request: APIRequestContext, path: string, actor: Actor) {
  await expect.poll(async () => {
    const response = await request.get(`/backend/api/v1/${path}`, { headers: actor.headers })
    expect(response.ok()).toBeTruthy()
    return z.object({ status: z.string() }).parse(await response.json()).status
  }, { timeout: 30_000 }).toBe('completed')
}
async function follow(request: APIRequestContext, follower: Actor, author: Actor) {
  const response = await request.post('/backend/api/v1/social/follows', { headers: follower.headers, data: { user_id: follower.id, followed_user_id: author.id } })
  expect(response.status()).toBe(202)
  const job = z.object({ operation_id: z.guid() }).parse(await response.json())
  await wait(request, `social/operations/${job.operation_id}`, follower)
}
async function publish(request: APIRequestContext, actor: Actor, text: string) {
  const response = await request.post('/backend/api/v1/posts', { headers: { ...actor.headers, 'Idempotency-Key': randomUUID() }, data: { user_id: actor.id, text, interests: ['datos'], media: [], visibility: 'public' } })
  expect(response.status()).toBe(202)
  const job = z.object({ operation_id: z.guid(), post_id: z.guid() }).parse(await response.json())
  await wait(request, `problems/operations/${job.operation_id}`, actor)
  return job.post_id
}
async function changeAccount(page: Page, reason: string) {
  await page.getByLabel('Motivo del cambio de cuenta').fill(reason)
  await page.getByRole('button', { name: 'Revisar cambio de cuenta' }).click()
  await expect(page.getByRole('group', { name: 'Confirmar cambio de cuenta', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Confirmar cambio de cuenta', exact: true }).click()
  await expect(page.getByText('Cambio de cuenta completado', { exact: true })).toBeVisible({ timeout: 30_000 })
}

test('P8 suspensión y reactivación reales: feed, sugerencias, presencia, sesión y moderación preservada', async ({ page, request, browser }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  const target = await account(request)
  const reader = await account(request)
  const recommender = await account(request)
  const admin = await account(request, 'admin')
  await follow(request, reader, target)
  await follow(request, recommender, reader)
  const text = `Publicación visible P8 ${randomUUID()}`
  const visiblePost = await publish(request, target, text)
  const hiddenPost = await publish(request, target, `Publicación moderada P8 ${randomUUID()}`)
  const reportResponse = await request.post('/backend/api/v1/moderation/reports', { headers: reader.headers, data: { post_id: hiddenPost, reason: 'other', description: 'QA P8 conservar moderación' } })
  expect(reportResponse.status()).toBe(201)
  const report = z.object({ id: z.guid() }).parse(await reportResponse.json())
  const hide = await request.post(`/backend/api/v1/moderation/reports/${report.id}/decision`, { headers: admin.headers, data: { decision: 'hide', reason: 'QA P8 moderación previa' } })
  expect(hide.status()).toBe(202)
  const hideJob = z.object({ operation_id: z.guid() }).parse(await hide.json())
  await wait(request, `moderation/operations/${hideJob.operation_id}`, admin)
  const conversationId = randomUUID()
  python(`import asyncio,json,sys
from datetime import UTC,datetime
from pymongo import AsyncMongoClient
from app.core.config import get_settings
async def main():
 s=get_settings(); assert s.app_env=='development'; c=AsyncMongoClient(s.mongodb_url)
 try:
  a=json.loads(sys.argv[1]); assert await c[s.mongodb_database].users.count_documents({'_id':{'$in':a['participants']},'username':{'$regex':'^qa_p8_'}})==2
  await c[s.mongodb_database].conversations.insert_one({'_id':a['id'],'participant_ids':a['participants'],'created_at':datetime.now(UTC)})
 finally: await c.close()
asyncio.run(main())`, [JSON.stringify({ id: conversationId, participants: [target.id, reader.id] })])
  const suggestionsPath = `/backend/api/v1/problems/4/recommendations/${recommender.id}`
  expect(z.array(z.guid()).parse(await (await request.get(suggestionsPath)).json())).toContain(target.id)
  const ownerContext = await browser.newContext({ baseURL: info.project.use.baseURL ?? 'http://127.0.0.1:4174', locale: 'es-AR', timezoneId: 'America/Buenos_Aires' })
  try {
    const ownerPage = await ownerContext.newPage()
    await login(ownerPage, target)
    await ownerPage.goto(`/cuentas/${target.id}`)
    await ownerPage.getByRole('button', { name: 'Renovar mi presencia' }).click()
    await expect(ownerPage.getByText('En línea', { exact: true })).toBeVisible()
    await login(page, admin)
    await page.getByRole('link', { name: 'Cuentas', exact: true }).click()
    await page.getByLabel('Identificador de usuario', { exact: true }).fill(target.id)
    const traceResponse = page.waitForResponse((response) => response.url().endsWith(`/accounts/${target.id}/trace`))
    await page.getByRole('button', { name: 'Consultar cuenta', exact: true }).click()
    const initial = traceSchema.parse(await (await traceResponse).json())
    expect(initial.active_conversations.map((conversation) => conversation.id)).toContain(conversationId)
    expect(initial.relationships.followers).toContain(reader.id)
    await expect(page.getByText(text, { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: info.outputPath('p8-active.png'), fullPage: true })
    await changeAccount(page, 'QA P8 suspensión confirmada')
    await page.reload()
    await expect(page.getByText('Cambio de cuenta completado', { exact: true })).toBeVisible()
    expect((await request.get(`/backend/api/v1/posts/${visiblePost}`)).status()).toBe(404)
    expect((await request.get(`/backend/api/v1/feeds/${target.id}`, { headers: target.headers })).status()).toBe(401)
    const feed = await request.get(`/backend/api/v1/feeds/${reader.id}`, { headers: reader.headers })
    expect(z.object({ items: z.array(postSchema) }).parse(await feed.json()).items).toHaveLength(0)
    expect(z.array(z.guid()).parse(await (await request.get(suggestionsPath)).json())).not.toContain(target.id)
    await ownerPage.getByRole('button', { name: 'Renovar mi presencia' }).click()
    await expect(ownerPage.getByRole('heading', { name: 'Iniciá sesión' })).toBeVisible()
    expect(await ownerPage.evaluate(() => sessionStorage.getItem('niche.session.token'))).toBeNull()
    await page.getByRole('link', { name: 'Consultar cuenta afectada' }).click()
    await expect(page.getByText('Suspendida', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Sin presencia activa', { exact: true })).toBeVisible()
    await expect(page.getByText('No hay publicaciones visibles para esta cuenta.')).toBeVisible()
    await expect(page.getByText(conversationId, { exact: true })).toBeVisible()
    await expect(page.getByText('Oculta por suspensión · Oculta por moderación', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: info.outputPath('p8-suspended.png'), fullPage: true })
    await changeAccount(page, 'QA P8 revisión favorable')
    expect((await request.get(`/backend/api/v1/posts/${visiblePost}`)).status()).toBe(200)
    expect((await request.get(`/backend/api/v1/posts/${hiddenPost}`)).status()).toBe(404)
    expect((await request.get(`/backend/api/v1/users/me`, { headers: target.headers })).status()).toBe(401)
    expect(z.array(z.guid()).parse(await (await request.get(suggestionsPath)).json())).toContain(target.id)
    const restoredFeed = await request.get(`/backend/api/v1/feeds/${reader.id}`, { headers: reader.headers })
    expect(z.object({ items: z.array(postSchema) }).parse(await restoredFeed.json()).items.map((post) => post.id)).toEqual([visiblePost])
    await page.getByRole('link', { name: 'Consultar cuenta afectada' }).click()
    await expect(page.getByText(text, { exact: true })).toBeVisible()
    await expect(page.getByText('Sin presencia activa', { exact: true })).toBeVisible()
    await page.screenshot({ path: info.outputPath('p8-reactivated.png'), fullPage: true })
    await login(ownerPage, target)
    await ownerPage.goto(`/cuentas/${target.id}`)
    await expect(ownerPage.getByText('Sin presencia activa', { exact: true })).toBeVisible()
    await ownerPage.getByRole('button', { name: 'Renovar mi presencia' }).click()
    await expect(ownerPage.getByText('En línea', { exact: true })).toBeVisible()
    expect(errors).toEqual([])
  } finally { await ownerContext.close() }
})

test('P8 privacidad de la traza y protección de comandos y autosuspensión', async ({ page, request }, info) => {
  const target = await account(request)
  const other = await account(request)
  const admin = await account(request, 'admin')
  expect((await request.get(`/backend/api/v1/accounts/${target.id}/trace`, { headers: other.headers })).status()).toBe(403)
  expect((await request.post(`/backend/api/v1/accounts/${target.id}/suspend`, { headers: target.headers, data: { reason: 'No permitido' } })).status()).toBe(403)
  expect((await request.post(`/backend/api/v1/accounts/${admin.id}/suspend`, { headers: admin.headers, data: { reason: 'No permitido' } })).status()).toBe(409)
  await login(page, other)
  await page.goto(`/cuentas/${target.id}`)
  await expect(page.getByRole('heading', { name: 'Trazabilidad privada' })).toBeVisible()
  await page.getByRole('link', { name: 'Consultar mi cuenta' }).click()
  await expect(page.getByText('No hay conversaciones activas registradas.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Revisar cambio de cuenta' })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('p8-own-empty.png'), fullPage: true })
})

test('P8 compensación real no informa suspensión completada', async ({ page, request }, info) => {
  const target = await account(request)
  const admin = await account(request, 'admin')
  const response = await request.post(`/backend/api/v1/accounts/${target.id}/suspend`, { headers: { ...admin.headers, 'Idempotency-Key': randomUUID(), 'X-Fail-At-Step': 'redis_close_presence' }, data: { reason: 'QA P8 compensación' } })
  expect(response.status()).toBe(202)
  const job = accountJobSchema.parse(await response.json())
  await login(page, admin)
  await page.goto(`/cuentas/operaciones/${job.operation_id}`)
  await expect(page.getByText('Cambio de cuenta cancelado', { exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('Cambio de cuenta completado', { exact: true })).toHaveCount(0)
  const trace = await request.get(`/backend/api/v1/accounts/${target.id}/trace`, { headers: admin.headers })
  expect(traceSchema.parse(await trace.json()).profile?.account_status).toBe('active')
  await page.screenshot({ path: info.outputPath('p8-compensated.png'), fullPage: true })
  await expect(page.getByRole('button', { name: 'Reintentar recuperación', exact: true })).toHaveCount(0)
  await expect(page.getByText(/La compensación terminó/)).toBeVisible()
})
