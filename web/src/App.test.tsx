import '@testing-library/jest-dom/vitest'

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { defaultPlatformSettings } from './settings/defaults'

vi.mock('./settings/useSettings', () => ({
  useSettings: () => ({
    platformSettings: {
      ...defaultPlatformSettings,
      platform_behavior: {
        ...defaultPlatformSettings.platform_behavior,
        preferred_landing_page: 'overview',
      },
    },
    appearance: {
      ...defaultPlatformSettings.appearance,
      theme_preset: 'default',
      reduced_motion: true,
      layout_width: 'standard',
    },
    loading: false,
  }),
}))

vi.mock('./pages/MarketOverviewPage', () => ({
  MarketOverviewPage: () => <div data-testid="market-overview-page" />,
}))

import App, { NAV_ITEMS } from './App'

describe('App', () => {
  it('puts Overview first in the nav order', () => {
    expect(NAV_ITEMS[0].label).toBe('Overview')
    expect(NAV_ITEMS[0].to).toBe('/market-overview')
  })

  it('redirects the root route to the market overview landing page by default', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByTestId('market-overview-page')).toBeInTheDocument()
    const navLinks = screen.getAllByRole('link', { name: /Overview|Backtests|Models|Data|Scanners|Contracts|Runtime|Chart|Settings/ })
    expect(navLinks[0]).toHaveTextContent('Overview')
  })
})
