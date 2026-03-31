import { act, renderHook, waitFor } from '@testing-library/react'

import * as api from '@/api'
import { useDesireCatalog } from '@/hooks/use-desire-catalog'

vi.mock('@/api', () => ({
  fetchDesireCatalog: vi.fn(),
}))

const makeDeferred = <T,>() => {
  let resolve!: (value: T | PromiseLike<T>) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

describe('useDesireCatalog', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads catalog items from the API', async () => {
    vi.mocked(api.fetchDesireCatalog).mockResolvedValue({
      items: [
        {
          id: 'information_hunger',
          display_name: 'information hunger',
          maslow_level: 1,
        },
      ],
    })

    const { result } = renderHook(() => useDesireCatalog())

    await waitFor(() => {
      expect(result.current).toEqual([
        {
          id: 'information_hunger',
          display_name: 'information hunger',
          maslow_level: 1,
        },
      ])
    })
  })

  it('ignores a late catalog response after unmount', async () => {
    const deferred = makeDeferred<{
      items: {
        id: string
        display_name: string
        maslow_level: number
      }[]
    }>()
    vi.mocked(api.fetchDesireCatalog).mockReturnValue(deferred.promise)

    const { result, unmount } = renderHook(() => useDesireCatalog())

    unmount()

    await act(async () => {
      deferred.resolve({
        items: [
          {
            id: 'social_thirst',
            display_name: 'social thirst',
            maslow_level: 1,
          },
        ],
      })
      await deferred.promise
    })

    expect(result.current).toEqual([])
  })
})
