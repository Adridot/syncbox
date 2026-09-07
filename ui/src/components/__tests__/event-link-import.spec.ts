import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { i18n } from '../../i18n'
import { api, ApiError } from '../../api/client'
import EventLinkImport from '../EventLinkImport.vue'

vi.mock('../../api/client', async (original) => ({ ...await original<typeof import('../../api/client')>(), api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('../../shell', () => ({ openExternal: vi.fn().mockResolvedValue(undefined) }))
const wrappers: ReturnType<typeof mount>[] = []
const row = (state = 'ready') => ({ id: 'preview-1', state, source_provider: 'youtube', canonical_url: 'https://www.youtube.com/playlist?list=PL1234567890', manifest: { entries: [
  { entry_key: '1:abc', position: 1, item_id: 'abc', title: 'First remix', available: true },
  { entry_key: '2:abc', position: 2, item_id: 'abc', title: 'Repeated remix', available: true, repeated: true },
  { entry_key: '3:def', position: 3, item_id: 'def', title: 'Private', available: false },
  { entry_key: '4:ghi', position: 4, item_id: 'ghi', title: 'Removed', available: true, existing_status: 'removed' },
  { entry_key: '5:jkl', position: 5, item_id: 'jkl', title: 'Second remix', available: true },
] }, result: state === 'committed' ? { added: 2 } : null })
async function setup(history = true, state = 'ready') {
  vi.mocked(api.get).mockImplementation(async path => path.endsWith('/link-imports') ? { imports: history ? [row(state)] : [] } : row(state))
  const wrapper = mount(EventLinkImport, { props: { eventId: 1 }, global: { plugins: [i18n], stubs: { RouterLink: true } } })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(value => value.text() === text)!
beforeEach(() => vi.clearAllMocks())
afterEach(() => { wrappers.forEach(wrapper => wrapper.unmount()); wrappers.length = 0; vi.useRealTimers() })

test('restores a preview in source order, excludes duplicate/private/removed entries, and commits only the selected subset', async () => {
  const wrapper = await setup()
  expect(wrapper.findAll('.entry span').map(value => value.text())).toEqual(['1. First remix', '2. Repeated remix', '3. Private', '4. Removed', '5. Second remix'])
  const checks = wrapper.findAll('.entry input')
  expect(checks.map(value => (value.element as HTMLInputElement).checked)).toEqual([true, false, false, false, true])
  expect(checks.map(value => value.attributes('disabled') !== undefined)).toEqual([false, true, true, true, false])
  await checks[4]!.setValue(false)
  vi.mocked(api.post).mockResolvedValue({ added: 1 })
  vi.mocked(api.get).mockResolvedValue({ ...row('committed'), result: { added: 1 } })
  await button(wrapper, 'Add 1 track').trigger('click')
  await flushPromises()
  expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/events/1/link-imports/preview-1/commit', { selected_keys: ['1:abc'], readd_keys: [] })
  expect(wrapper.emitted('committed')).toHaveLength(1)
  expect(wrapper.text()).toContain('1 track added to the event.')
})

test('requires an explicit removed-item opt-in and preserves the re-add choice in confirmation', async () => {
  const wrapper = await setup()
  await wrapper.get('.actions input').setValue(true)
  await button(wrapper, 'Select all available').trigger('click')
  await button(wrapper, 'Add 3 tracks').trigger('click')
  await flushPromises()
  expect(api.post).toHaveBeenCalledWith(expect.stringContaining('/commit'), { selected_keys: ['1:abc', '4:ghi', '5:jkl'], readd_keys: ['4:ghi'] })
})

test('retains the pasted URL on ambiguity and submits the explicit playlist choice with the same request token', async () => {
  const wrapper = await setup(false)
  const url = 'https://www.youtube.com/watch?v=f7NwyBnIRTE&list=PL1234567890'
  await wrapper.get('input').setValue(url)
  vi.mocked(api.post).mockRejectedValueOnce(new ApiError(409, { error: 'conflict', message: 'video_or_playlist_choice_required' })).mockResolvedValue(row())
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect((wrapper.get('input').element as HTMLInputElement).value).toBe(url)
  await button(wrapper, 'The playlist').trigger('click')
  await flushPromises()
  const calls = vi.mocked(api.post).mock.calls
  expect(calls[1]![1]).toMatchObject({ url, choice: 'playlist', request_token: (calls[0]![1] as { request_token: string }).request_token })
  expect(calls.every(([path]) => !path.includes('acquisition'))).toBe(true)
})

test('a dismissed preview cannot reappear when its in-flight poll completes', async () => {
  vi.useFakeTimers()
  const wrapper = await setup(true, 'resolving')
  let complete!: (value: unknown) => void
  vi.mocked(api.get).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  await vi.advanceTimersByTimeAsync(500)
  vi.mocked(api.delete).mockResolvedValue({})
  await button(wrapper, 'Dismiss preview').trigger('click')
  await flushPromises()
  complete(row())
  await flushPromises()
  expect(wrapper.find('.preview').exists()).toBe(false)
  expect(vi.getTimerCount()).toBe(0)
})

test('reopens a committed result without adding or downloading again', async () => {
  const wrapper = await setup(true, 'committed')
  expect(wrapper.text()).toContain('2 tracks added to the event.')
  expect(api.post).not.toHaveBeenCalled()
  expect(wrapper.find('.entries').exists()).toBe(false)
})

test('a restored failure can be retried without creating a new import or downloading audio', async () => {
  const wrapper = await setup(true, 'failed')
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  vi.mocked(api.post).mockResolvedValue({})
  vi.mocked(api.get).mockResolvedValue(row())
  await button(wrapper, 'Retry preview').trigger('click')
  await flushPromises()
  expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/events/1/link-imports/preview-1/retry')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(button(wrapper, 'Add 2 tracks').exists()).toBe(true)
})
