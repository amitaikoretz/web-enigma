import '@testing-library/jest-dom/vitest'

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

import { ReturnForecastModelsListPage } from './ReturnForecastModelsListPage'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}{location.search}</div>
}

describe('ReturnForecastModelsListPage', () => {
  it('redirects to the unified models list with the return filter preserved', async () => {
    render(
      <MemoryRouter initialEntries={['/models/returns']}>
        <Routes>
          <Route path="/models/returns" element={<ReturnForecastModelsListPage />} />
          <Route path="/models" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByTestId('location')).toHaveTextContent('/models?family=returns')
  })
})
