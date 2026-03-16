# ui — Claude Context

React 18 + TypeScript + Vite frontend for JobFinder. Served by FastAPI in production; runs on its own Vite dev server during development.

## Dev Workflow
```bash
# Needs Node 20+  (nvm use 20)
pnpm install        # first time
pnpm dev            # http://localhost:5173 — proxies /api → localhost:8000
pnpm build          # outputs to ui/dist/ — picked up automatically by `jobfinder serve`
```

## Env Vars
Two separate env files; both are gitignored:

| File | Gitignored by | Purpose |
|------|--------------|---------|
| `ui/.env.local` | `ui/.gitignore` (`*.local`) | Real Supabase credentials for local dev |
| `ui/.env.example` | not ignored — committed | Documents required vars with empty values |

Required vars (copy `.env.example` → `.env.local` and fill in):
```
VITE_SUPABASE_URL=https://<project-id>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
```
If these are absent, `lib/supabase.ts` returns `null` → "Run Managed" card is disabled, app runs in local-only mode.

## Run Modes

The app has two run modes selected on the landing page, persisted in `localStorage["verdantme-mode"]`:

| Mode | Auth | Storage | When to use |
|------|------|---------|-------------|
| `"local"` | None | Backend JSON files | Development, offline, no Supabase creds |
| `"managed"` | Supabase email/password | Supabase Postgres (RLS) | Production, cloud sync |

**Mode selection page** (`ModeSelectionPage.tsx`) is shown on first visit (when `localStorage` has no entry). Users can switch back via the **⇄ Switch Mode** button in the footer.

## File Map
```
src/
  main.tsx              # React root — ModeProvider > AuthProvider > QueryClientProvider > App
  App.tsx               # Three-tab shell; routes to ModeSelectionPage / LoginPage / tabs by mode+auth
  contexts/
    ModeContext.tsx      # AppMode ("local"|"managed"|null), localStorage-backed, clearMode() flushes cache
  lib/
    api.ts              # axios client + ALL TypeScript types + typed fetch functions
                        # JWT attached only when mode="managed" (reads localStorage directly)
    queryClient.ts      # TanStack Query client (staleTime=5min, retry=1)
    supabase.ts         # Supabase JS client singleton; null if VITE_SUPABASE_URL not set
  components/
    ModeSelectionPage.tsx  # Landing page — "Run Local" / "Run Managed" cards
    AuthProvider.tsx       # Supabase auth context; skipped entirely when mode="local"
    LoginPage.tsx          # Email/password sign-in + sign-up; shown only in managed mode
    ResumeTab.tsx          # Drag-and-drop .txt upload → parsed skills/titles card
    CompaniesTab.tsx       # max_companies + provider form → company table
    RolesTab.tsx           # Filter form → sortable TanStack Table + flagged callout
    Footer.tsx             # onSwitchMode prop → renders "⇄ Switch Mode" button
    ui/                    # shadcn/ui primitives (button, card, tabs, badge, input, label)
  tests/
    setup.ts             # jest-dom + localStorage mock + ResizeObserver stub
    App.test.tsx         # Header, scroll, tabs, footer — seeds localStorage to "local" mode
    ResumeTab.test.tsx   # Upload/display tests
    api.test.ts          # API helper unit tests
vite.config.ts           # @ alias → src/; /api proxy → :8000
tailwind.config.js       # Tailwind v4 content paths + shadcn color tokens
tsconfig.app.json        # paths: "@/*" → "./src/*"
```

## Key Patterns

**Mode context** — read anywhere with `useMode()`:
```typescript
const { mode, setMode, clearMode } = useMode();
// mode: "local" | "managed" | null
// clearMode() also calls queryClient.clear() — prevents data bleed between modes
```

**Auth context** — read anywhere with `useAuth()`:
```typescript
const { user, session, signIn, signUp, signOut, loading } = useAuth();
// user is always null in local mode (auth is skipped)
```

**Data fetching** — always use TanStack Query:
- `useQuery` for GET (preloads cached data on mount): `useQuery({ queryKey: ["roles"], queryFn: getRoles, retry: false })`
- `useMutation` for POST (discover actions): `useMutation({ mutationFn: ..., onSuccess, onError })`
- On success, push fresh data into cache: `qc.setQueryData(["roles"], data)` — avoids a redundant GET

**API client** (`lib/api.ts`):
- All types and fetch functions live here — single source of truth
- Add a new endpoint: add the TypeScript interface, then an `async function` using the `api` axios instance
- JWT is auto-attached to every request when `mode === "managed"`; local mode sends no auth header
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

## Writing Tests

Tests bypass mode selection by seeding localStorage before render:
```typescript
import { ModeProvider } from "@/contexts/ModeContext";

beforeEach(() => { localStorage.setItem("verdantme-mode", "local"); });
afterEach(() => { localStorage.clear(); });

function renderWithProviders(ui: ReactNode) {
  return render(
    <ModeProvider>
      <AuthProvider>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          {ui}
        </QueryClientProvider>
      </AuthProvider>
    </ModeProvider>
  );
}
```
Always mock supabase as null in tests: `vi.mock("@/lib/supabase", () => ({ supabase: null }))`.
