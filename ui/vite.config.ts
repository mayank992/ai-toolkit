import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const here = (p: string) => decodeURIComponent(new URL(p, import.meta.url).pathname);

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Feature views import the shell's contract as "@toolkit/ui" (src/sdk.ts).
    alias: { "@toolkit/ui": here("./src/sdk.ts") },
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:7319" },
  },
});
