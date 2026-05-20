import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// ... baki imports

export default defineConfig({
  plugins: [react()],
  // Is server block ko dhundh kar update karna hai 👇
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: ['munshiai.co.in', 'www.munshiai.co.in'], // YEH LINE ADD KAREIN
  }
})
