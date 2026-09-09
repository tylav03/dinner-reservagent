import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Tailwind v4 is wired in as a Vite plugin (no tailwind.config.js / postcss needed
// unless we customize the theme).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173, // must match the backend's CORS_ORIGINS
  },
});
