import '@testing-library/jest-dom/vitest'

import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const fetchMock = vi.fn()

vi.stubGlobal('fetch', fetchMock)

import { BacktestConfigInspector } from './BacktestConfigInspector'

describe('BacktestConfigInspector', () => {
  beforeEach(() => {
    fetchMock.mockReset()
  })

  it('disables YAML download actions until the backtest completes', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      text: async () => 'name: demo',
    })

    render(
      <BacktestConfigInspector
        backtestId="bt-1"
        inputConfigPath={null}
        configSha256="abcdef0123456789"
        downloadable={false}
      />,
    )

    await waitFor(() => expect(screen.getByText('Loading configuration…')).toBeInTheDocument())

    expect(await screen.findByText('Open YAML')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('Download')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('YAML downloads are only enabled after a backtest completes successfully.')).toBeInTheDocument()
  })
})
