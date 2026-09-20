import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import App from './App.tsx'

afterEach(() => {
  cleanup()
})

describe('App placeholder', () => {
  it('renders the scaffold heading and POC safety line', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /eldercare vision/i }),
    ).toBeDefined()
    expect(screen.getByText(/frontend scaffold.*p0-003/i)).toBeDefined()
    expect(screen.getByText(/not a medical device/i)).toBeDefined()
  })
})
