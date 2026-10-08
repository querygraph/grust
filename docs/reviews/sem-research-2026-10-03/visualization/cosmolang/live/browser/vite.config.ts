import { defineConfig } from 'vite';
export default defineConfig({build:{target:'es2022'},server:{proxy:{'/cosmolang':'http://127.0.0.1:18767','/objects':'http://127.0.0.1:18767','/mcp':'http://127.0.0.1:18767'}}});
