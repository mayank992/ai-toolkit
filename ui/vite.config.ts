import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const here = (p: string) => decodeURIComponent(new URL(p, import.meta.url).pathname);

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Module UIs live in modules/<name>/ui and import "@toolkit/ui" plus React. They have no
    // node_modules of their own, so dedupe makes React resolve from this package for every importer.
    alias: { "@toolkit/ui": here("./src/sdk.ts") },
    dedupe: ["react", "react-dom"],
  },
  server: {
    fs: { allow: [here("..")] },
    proxy: { "/api": "http://127.0.0.1:7319" },
  },
});
