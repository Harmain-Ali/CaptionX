import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Python backend runs on :8000. In dev, Vite proxies /api there so there are no CORS surprises.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
});
