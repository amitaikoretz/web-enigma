import '@testing-library/jest-dom/vitest'

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { ModelsLandingPage } from './ModelsLandingPage'

describe('ModelsLandingPage', () => {
  it('links to the risk and return forecast families', () => {
    render(
      <MemoryRouter initialEntries={['/models']}>
        <Routes>
          <Route path="/models" element={<ModelsLandingPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Models')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open risk models/i })).toHaveAttribute('href', '/models/risk')
    expect(screen.getByRole('link', { name: /open return forecasts/i })).toHaveAttribute(
      'href',
      '/models/returns',
    )
  })
})
