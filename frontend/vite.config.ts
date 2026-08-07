import { defineConfig, loadEnv } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const backendEnv = loadEnv(mode, '..', '')
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000'
  const proxyHeaders = backendEnv.API_AUTH_TOKEN
    ? { 'x-bitbox-token': backendEnv.API_AUTH_TOKEN }
    : undefined

  return {
    plugins: [
      react(),
      tailwindcss(),
    ],
    server: {
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true, headers: proxyHeaders },
        '/health': { target: proxyTarget, changeOrigin: true },
      },
    },
  };
});
