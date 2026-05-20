export default defineConfig({
  // Baaki plugins wagaira yahan honge...
  plugins: [react()],
  
  // Yeh naya server block add karna hai 👇
  server: {
    host: '0.0.0.0',
    allowedHosts: ['munshiai.co.in', 'www.munshiai.co.in']
  }
})
