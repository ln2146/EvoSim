import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { startDynamicDemoWithPreset } from './startDemo'
import { setAttackFlag, setAttackMode, setAftercareFlag, setModerationFlag } from '../../services/api'

vi.mock('../../services/api', () => ({
  setAttackMode: vi.fn(),
  setAttackFlag: vi.fn(),
  setAftercareFlag: vi.fn(),
  setModerationFlag: vi.fn(),
}))

describe('startDynamicDemoWithPreset', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts demo and replays the same preset sync chain used by dynamic demo', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        json: async () => ({ success: true }),
      })
      .mockResolvedValueOnce({
        json: async () => ({ success: true }),
      })
      .mockResolvedValueOnce({
        json: async () => ({ success: true }),
      })

    vi.mocked(setAttackMode).mockResolvedValue(undefined as never)
    vi.mocked(setAttackFlag).mockResolvedValue({ attack_enabled: true } as never)
    vi.mocked(setAftercareFlag).mockResolvedValue({ aftercare_enabled: false } as never)
    vi.mocked(setModerationFlag).mockResolvedValue({ moderation_enabled: true } as never)

    const resultPromise = startDynamicDemoWithPreset({
      enableAttack: true,
      attackMode: 'swarm',
      enableAftercare: false,
      enableModeration: true,
      enableEvoCorps: true,
      fetchImpl: fetchMock as typeof fetch,
    })

    await expect(resultPromise).resolves.toMatchObject({ success: true })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/config/moderation',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/dynamic/start',
      expect.objectContaining({ method: 'POST' }),
    )

    await vi.advanceTimersByTimeAsync(3000)
    await Promise.resolve()

    expect(setAttackMode).toHaveBeenCalledWith('swarm')
    expect(setAttackFlag).toHaveBeenCalledWith(true)
    expect(setAftercareFlag).toHaveBeenCalledWith(false)
    expect(setModerationFlag).toHaveBeenCalledWith(true)
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/dynamic/opinion-balance/start',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
