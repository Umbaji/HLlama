# HLlama Admin Dashboard

Back-office application for the HLlama connected-health platform (sexual and reproductive
health assistant by Umbaji). Provides statistics visualization, user management, question
moderation, documentary-base review, and activity logging for administrators.

## Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 16 (App Router) |
| Language | TypeScript (strict mode) |
| Styling | Tailwind CSS v4 |
| State management | TanStack React Query v5 |
| HTTP client | Axios (interceptors for auth and error handling) |
| Internationalization | next-intl (French / English) |
| Icons | Lucide React |

## Project Architecture

```
src/
├── app/
│   ├── layout.tsx                     Root layout (pass-through)
│   ├── page.tsx                       Redirect to /{defaultLocale}/overview
│   └── [locale]/
│       ├── layout.tsx                 Locale provider (NextIntlClientProvider)
│       ├── (auth)/
│       │   └── login/page.tsx         Admin login page
│       └── (dashboard)/
│           ├── layout.tsx             Sidebar + Header + auth guard
│           ├── overview/page.tsx      Statistics dashboard (KPI cards)
│           ├── users/page.tsx         User management (CRUD, roles)
│           ├── questions/page.tsx     Question moderation
│           ├── knowledge/page.tsx     Documentary base review
│           ├── feedback/page.tsx      User feedback summary and answers
│           ├── logs/page.tsx          Activity audit trail
│           └── settings/page.tsx      Profile, security, exports, system
├── components/
│   ├── charts/
│   │   └── stat-grid.tsx             KPI stat cards
│   ├── layout/
│   │   ├── sidebar.tsx               Navigation sidebar
│   │   ├── header.tsx                Top bar with locale switch
│   │   └── providers.tsx             React Query provider
│   └── ui/
│       └── button.tsx                Shared button component
├── features/
│   └── knowledge/                    Documentary base review (components, screens, services, types)
├── i18n/
│   ├── config.ts                     Locale definitions (fr, en)
│   ├── navigation.ts                 Localized Link/useRouter/usePathname
│   └── request.ts                    Server-side message loader
├── lib/
│   ├── api/
│   │   ├── client.ts                 Axios instance + interceptors + ApiError class
│   │   ├── auth.ts                   Login, getCurrentUser
│   │   ├── stats.ts                  Overview stats
│   │   ├── users.ts                  User CRUD + admin actions
│   │   ├── management.ts            Questions, logs, CSV exports
│   │   └── feedback.ts              Feedback answers and aggregates
│   ├── hooks/
│   │   └── use-auth.ts              Authentication hook (login, logout, checkAuth)
│   ├── types/
│   │   └── api.ts                   TypeScript interfaces for all API responses
│   └── utils/
│       ├── cn.ts                    clsx + tailwind-merge
│       └── format.ts               Date formatting with locale support
├── messages/
│   ├── en/                          English translations (domain files)
│   └── fr/                          French translations (domain files)
└── proxy.ts                         next-intl middleware (locale routing)
```

## Features

### Dashboard (Overview)

- KPI cards: total users, active users, questions, admins
- Secondary metrics: new users (7d/30d), questions (7d/30d)

### User Management

- Paginated user table with role and status indicators
- Filter tabs: All / Users only / Admins only
- Actions: activate, deactivate, promote to admin, demote, soft-delete
- Role badge (Admin) with visual distinction

### Question Moderation

- Paginated list of all user questions
- Display user name and phone number
- Delete action for inappropriate content

### Documentary Base

- Review the knowledge base: scan, differences against the source, apply, supervise

### Activity Logs

- Chronological audit trail of all admin actions
- Shows admin name, action type, target, details, timestamp

### User Feedback

- Usefulness answers ("Utile / Moyen / Pas utile"), share found useful, breakdown
- Free comments and every answer, filterable by question

### Settings

- Profile display (name, email)
- Password change form with validation
- System info (API URL, version, status indicator)
- CSV export (users, questions) - downloads files directly
- Notification toggles (visual, for future backend integration)
- Danger zone (clear logs - placeholder)

## Internationalization

All text is translated via `useTranslations()` from next-intl. No hardcoded strings.

Translation files are organized by domain:

| File | Scope |
|------|-------|
| `common.json` | Shared UI (buttons, status, pagination, API message keys) |
| `auth.json` | Login page |
| `dashboard.json` | Overview stats |
| `users.json` | User management page |
| `questions.json` | Question moderation page |
| `knowledge.json` | Documentary base page |
| `logs.json` | Activity logs page |
| `settings.json` | Settings page |
| `feedback.json` | User feedback page |

Backend API message keys (e.g. `INVALID_CREDENTIALS`, `USER_NOT_FOUND`) are translated in `common.json > apiMessages`.

## API Integration

The dashboard connects to the HLlama backend API. The Axios client (`src/lib/api/client.ts`) handles:

- Automatic `Authorization: Bearer <token>` header injection
- 401 response interception (clears token, redirects to login)
- Error normalization via `ApiError` class with `code` property matching backend message keys
- Typed responses using generics (`ApiResponse<T>`)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend API base URL (e.g. `http://localhost:8000`) |

## Development

```bash
npm install
cp .env.example .env.local   # Set NEXT_PUBLIC_API_URL
npm run dev
```

Open http://localhost:3000 (redirects to http://localhost:3000/fr/overview).

## Checks

```bash
npm run typecheck                 # tsc --noEmit
npm run lint -- --max-warnings=0  # eslint, zero warnings
npm run build
```

Run all three before opening a pull request; the `Checks` workflow runs exactly
these on every pull request to `develop` and `main`, on Node 20, the version the
Dockerfile ships.

Zero warnings is deliberate. A warning nobody has to clear accumulates until the
output is noise and a real one goes unread.

The build is the only one of the three that exercises the server components and
the route tree: `tsc` and `eslint` both pass on a page that cannot render.

## Build

```bash
npm run build
```

Output is in `.next/standalone` (configured for Docker deployment).

## Docker

```bash
docker build -t hllama-admin \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 .
docker run -p 3010:3010 hllama-admin
```

Or use `admin/docker-compose.yml`, which builds the back office and serves it on
`http://localhost:3010`; point `NEXT_PUBLIC_API_URL` at a running backend.

## TypeScript Configuration

Strict mode is enforced with these additional checks:

- `noUncheckedIndexedAccess` - bracket access returns `T | undefined`
- `noImplicitReturns` - all code paths must return
- `noFallthroughCasesInSwitch` - switch cases must break
- `noPropertyAccessFromIndexSignature` - forces bracket notation for index signatures
- `allowJs: false` - no JavaScript files allowed

## Design Principles

- Flat, compact layout with thin borders (no heavy shadows or cards)
- Small typography (`text-xs` to `text-sm`) with semibold values
- Tight spacing (4px grid: `gap-2`, `p-3`, `p-4`)
- Professional color palette: blue, emerald, amber, indigo, rose
- Responsive: tables scroll horizontally, grids collapse on mobile
- Separation of concerns: UI components, API layer, hooks, types
