import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
			},
			// Built to static files that the Engine serves; every route falls back to the SPA shell.
			adapter: adapter({ fallback: 'index.html' })
		})
	],
	server: {
		// In development the UI runs on Vite and talks to the Engine API.
		proxy: { '/api': 'http://127.0.0.1:8321' }
	}
});
