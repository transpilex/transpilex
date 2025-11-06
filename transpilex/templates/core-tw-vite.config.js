import {defineConfig} from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
    appType: 'custom',
    base: '/dist/',
    publicDir: false,
    build: {
        manifest: true,
        emptyOutDir: true,
        outDir: 'wwwroot/dist',
        rollupOptions: {
            input: [
                "Assets/js/vendor.js",
                "Assets/js/app.js"
            ],
        }
    },
    plugins: [tailwindcss()]
});