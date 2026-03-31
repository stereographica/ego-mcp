import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }
          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/scheduler/')
          ) {
            return 'react-vendor'
          }
          if (
            id.includes('@radix-ui') ||
            id.includes('class-variance-authority') ||
            id.includes('tailwind-merge') ||
            id.includes('clsx')
          ) {
            return 'ui-vendor'
          }
          if (
            id.includes('recharts') ||
            id.includes('/d3-') ||
            id.includes('victory') ||
            id.includes('internmap') ||
            id.includes('re-resizable')
          ) {
            return 'chart-vendor'
          }
          return undefined
        },
      },
    },
  },
})
