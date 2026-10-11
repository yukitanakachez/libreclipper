# Clipper review app

The browser side of `clipper serve`: React, TypeScript and Vite. It talks to the local API
(`/api`, `/media`) that `clipper/web` serves.

```bash
npm install
npm run build     # writes dist/, which `clipper serve` serves
npm test          # Vitest + Testing Library
npm run lint      # oxlint
npm run dev       # Vite dev server; proxies the API to a running `clipper serve`
```
