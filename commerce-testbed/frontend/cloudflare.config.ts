import { defineConfig } from "cf/config";

export default defineConfig({
  worker: {
    "name": "frontend",
    "compatibilityDate": "2026-10-28",
    "observability": {
      "enabled": true,
      "traces": {
        "enabled": true
      }
    },
    "assets": {
      "notFoundHandling": "single-page-application"
    }
  }
});
