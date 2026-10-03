import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    // Component tests run against the deterministic fixture transport.
    env: { VITE_USE_MOCK: 'true' },
  },
})
