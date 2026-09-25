# Control web app

The SvelteKit app every Control Client uses. It builds to static files, which the Engine serves at http://localhost:8321.

See the [main README](../README.md) for how Control works and how to run it, and [docs/design-system.md](../docs/design-system.md) before changing the UI.

```bash
npm install
npm run dev     # http://localhost:5173, forwards /api to a running Engine
npm run build   # what the Engine serves
npm run check   # lint, format, types, tests
```
