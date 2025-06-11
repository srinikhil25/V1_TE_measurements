import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    headers: {
      'Access-Control-Allow-Origin': '*',
    },
    proxy: {
      '/api': {
        target: 'https://37c9-133-70-80-52.ngrok-free.app',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path
      }
    }
  },
})
