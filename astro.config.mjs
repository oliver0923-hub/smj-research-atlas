import { defineConfig } from 'astro/config';
export default defineConfig({site: process.env.SITE_URL || 'https://oliver0923-hub.github.io', base:process.env.BASE_PATH || '/', output:'static', vite:{build:{emptyOutDir:false}}});
