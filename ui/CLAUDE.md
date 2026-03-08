# ui — Claude Context

React 18 + TypeScript + Vite frontend for JobFinder. Served by FastAPI in production; runs on its own Vite dev server during development.

## Dev Workflow
```bash
# Needs Node 20+  (nvm use 20)
pnpm install        # first time
pnpm dev            # http://localhost:5173 — proxies /api → localhost:8000
pnpm build          # outputs to ui/dist/ — picked up automatically by `jobfinder serve`
```

## File Map
```
src/
  main.tsx              # React root — wraps App in QueryClientProvider
  App.tsx               # Three-tab shell (shadcn/ui <Tabs>)
  lib/
    api.ts              # axios client + ALL TypeScript types + typed fetch functions
    queryClient.ts      # TanStack Query client (staleTime=5min, retry=1)
  components/
    ResumeTab.tsx        # Drag-and-drop .txt upload → parsed skills/titles card
    CompaniesTab.tsx     # max_companies + provider form → company table
    RolesTab.tsx         # Filter form → sortable TanStack Table + flagged callout
    ui/                  # shadcn/ui primitives (button, card, tabs, badge, input, label)
vite.config.ts           # @ alias → src/; /api proxy → :8000
tailwind.config.js       # Tailwind v4 content paths + shadcn color tokens
tsconfig.app.json        # paths: "@/*" → "./src/*"
```

## Key Patterns

**Data fetching** — always use TanStack Query:
- `useQuery` for GET (preloads cached data on mount): `useQuery({ queryKey: ["roles"], queryFn: getRoles, retry: false })`
- `useMutation` for POST (discover actions): `useMutation({ mutationFn: ..., onSuccess, onError })`
- On success, push fresh data into cache: `qc.setQueryData(["roles"], data)` — avoids a redundant GET

**API client** (`lib/api.ts`):
- All types and fetch functions live here — single source of truth
- Add a new endpoint: add the TypeScript interface, then an `async function` using the `api` axios instance
- Error shape from FastAPI: `{ response: { data: { detail: string } } }`

**Loading states**:
- Inline spinner for buttons: `<span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" />`
- Full-area spinner for long ops: centered `h-10 w-10` spinner with descriptive text below

**Sortable table** (RolesTab): uses `@tanstack/react-table` — `createColumnHelper`, `useReactTable`, `getCoreRowModel`, `getSortedRowModel`. Click column headers to sort; `↑`/`↓` indicators added inline.

## Adding a New Tab
1. Create `src/components/<Name>Tab.tsx`
2. Add typed fetch functions to `src/lib/api.ts`
3. Add `<TabsTrigger>` + `<TabsContent>` in `App.tsx`
4. New shadcn components: `pnpm dlx shadcn@latest add <component>` (needs Node 20)
