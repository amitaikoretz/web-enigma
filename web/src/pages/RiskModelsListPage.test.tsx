import '@testing-library/jest-dom/vitest'

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

import { RiskModelsListPage } from './RiskModelsListPage'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}{location.search}</div>
}

describe('RiskModelsListPage', () => {
  it('redirects to the unified models list with the risk filter preserved', async () => {
    render(
      <MemoryRouter initialEntries={['/models/risk']}>
        <Routes>
          <Route path="/models/risk" element={<RiskModelsListPage />} />
          <Route path="/models" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByTestId('location')).toHaveTextContent('/models?family=risk')
  })
})
