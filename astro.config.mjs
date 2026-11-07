import { defineConfig } from 'astro/config';
export default defineConfig({site: process.env.SITE_URL || 'https://smj-research-atlas-oliver.oliver0923.chatgpt.site', base:process.env.BASE_PATH || '/', output:'static', vite:{build:{emptyOutDir:false}}});
