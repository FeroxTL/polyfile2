import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    globals: true,
    // Используем node, так как тесты логические
    environment: 'node',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['core/**/*'],
      exclude: ['node_modules', 'vendor/**'],
    },
  },
})
