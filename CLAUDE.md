# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Factory Inventory Management System Demo — a Claude Code workshop app. Full-stack: Vue 3 frontend, Python FastAPI backend, all data in-memory (no database, no persistence, no auth beyond a mock).

> ⚠️ **This repository and any fork you create are PUBLIC.** Do not commit credentials, internal hostnames, or private registry URLs. `client/.npmrc` pins the public npm registry and `client/package-lock.json` is gitignored to prevent locally-configured registries from leaking into commits — leave both in place.

## Stack

- **Frontend**: Vue 3 + Composition API + Vite (port 3000)
- **Backend**: Python FastAPI + uv (port 8001)
- **Data**: JSON files in `server/data/` loaded once at startup via `server/mock_data.py` — nothing persists across a restart, and endpoints filter this in-memory data directly (no DB queries).

There are subdirectory `CLAUDE.md` files with detailed conventions and code templates — read them when working in that area rather than relying on this summary:
- `server/CLAUDE.md` — FastAPI endpoint/model patterns, filtering conventions, error handling
- `client/CLAUDE.md` — Vue 3 Composition API patterns, composable patterns, chart/styling conventions

## Commands

**Install:**
```bash
cd server && uv venv && uv sync
cd client && npm install
```

**Run (one command, macOS/Linux only):**
```bash
./scripts/start.sh   # starts both servers, logs to /tmp/inventory-*.log
./scripts/stop.sh    # kills both
```

**Run manually** (also required on Windows — the scripts are bash-only):
```bash
cd server && uv run python main.py     # http://localhost:8001, docs at /docs
cd client && npm run dev               # http://localhost:3000
```

**Test** (backend only — there is no frontend test suite):
```bash
cd tests
uv run pytest -v                                                  # all tests
uv run pytest backend/test_inventory.py -v                        # one file
uv run pytest backend/test_inventory.py::TestInventoryEndpoints::test_get_all_inventory -v  # one test
uv run pytest --cov=../server --cov-report=html                   # coverage
```
Tests live in `tests/backend/` (not under `server/`) and import the app via `sys.path` manipulation in `tests/backend/conftest.py`, which also provides the `client` TestClient fixture. When adding or editing tests here, follow `.claude/skills/backend-api-test/SKILL.md`.

**Build:**
```bash
cd client && npm run build   # output: client/dist/
```

## Architecture

### Filter system
Four filters — Time Period, Warehouse, Category, Order Status — are managed by the singleton composable `client/src/composables/useFilters.js` (module-level refs, not per-component state) and apply across views via query params: `warehouse`, `category`, `status`, `month`.
- `month` accepts either a specific month (`2025-01`) or a quarter (`Q1-2025`); quarter→month mapping is hardcoded to 2025 in `server/main.py`'s `QUARTER_MAP` — it silently matches nothing for other years.
- **Inventory has no time dimension.** `/api/inventory` doesn't accept `month`; only `warehouse`/`category`.

Data flow: Vue filter composable → `client/src/api.js` (axios) → FastAPI query params → `apply_filters`/`filter_by_month` in `server/main.py` (filters copies of the in-memory lists) → Pydantic `response_model` validation → Vue computed properties.

### Backend data model
- Pydantic models in `server/main.py` must stay in sync with the JSON shape in `server/data/*.json` — there's no migration path, just edit both.
- Backlog items are joined to purchase orders at request time: `GET /api/backlog` computes `has_purchase_order` per item by scanning `purchase_orders` for a matching `backlog_item_id` (see `get_backlog` in `main.py`).
- Orders carry `warehouse`/`category` directly (denormalized), so dashboard/report aggregates don't need to join against inventory.

### API endpoints
- `GET /api/inventory[/{id}]` — filters: `warehouse`, `category`
- `GET /api/orders[/{id}]` — filters: `warehouse`, `category`, `status`, `month`
- `GET /api/dashboard/summary` — all filters; computes inventory value, low-stock count, pending-orders count, total order value
- `GET /api/demand`, `/api/backlog` — no filters
- `GET /api/spending/{summary,monthly,categories,transactions}` — no filters
- `GET /api/reports/{quarterly,monthly-trends}` — computed from `orders`, not query-filterable
- `GET/POST/DELETE/PATCH /api/tasks`, `POST /api/purchase-orders`, `GET /api/purchase-orders/{backlog_item_id}` — referenced by `client/src/api.js` but not defined in the `server/main.py` shown by `grep`; check current `main.py` before assuming these exist.

### i18n
`client/src/composables/useI18n.js` is a hand-rolled translator (no vue-i18n dependency) reading `client/src/locales/{en,ja}.js`, with locale persisted to `localStorage['app-locale']`. Currency (`USD`/`JPY`) is derived from locale, not set independently. Product/customer/warehouse name translation is separate from the `t()` key lookup — see `translateProductName`/`translateCustomerName`/`translateWarehouse` in the same file.

### Mock auth & tasks
`client/src/composables/useAuth.js` provides a hardcoded `currentUser` (name/tasks vary by locale) with no real authentication — `logout()` just shows an alert. `App.vue` merges this mock user's `tasks` with real tasks fetched from `/api/tasks` into one list (`tasks` computed); toggling/deleting a task branches on whether its `id` exists in the mock list vs. came from the API, so the two sources need to stay disambiguable by ID.

### Revenue goal
Dashboard revenue goal is hardcoded in `client/src/views/Dashboard.vue` (`revenueGoal` computed): $800K/month, scaled by the number of months implied by the active time-period filter (so $9.6M when viewing all 12 months).

## Critical Tool Usage Rules

### Subagents
Use the Task tool with these specialized subagents for appropriate tasks:

- **vue-expert**: Use for Vue 3 frontend features, UI components, styling, and client-side functionality
  - Examples: Creating components, fixing reactivity issues, performance optimization, complex state management
  - **MANDATORY RULE: ANY time you need to create or significantly modify a .vue file, you MUST delegate to vue-expert**
- **code-reviewer**: Use after writing significant code to review quality and best practices
- **security-auditor**: Fast, changed-files-only security pass (secrets, XSS via `v-html`/`innerHTML`, missing input validation)
- **Explore**: Use for understanding codebase structure, searching for patterns, or answering questions about how components work
- **general-purpose**: Use for complex multi-step tasks or when other agents don't fit

### Skills
- **backend-api-test** skill: Use when writing or modifying tests in `tests/backend` directory with pytest and FastAPI TestClient

### Custom slash commands (`.claude/commands/`)
- `/start`, `/stop` — start/stop both dev servers, killing anything already on 3000/8001
- `/test` — run the full test suite (frontend + backend + lint) and report
- `/optimize` — scan for dead code/unused deps and clean it up
- `/demo-branch` — create `demo-branch`/`demo-branch-2`/... for throwaway demo work
- `/reset-branch` — **destructive**: switches to `main`, hard-deletes the current branch (commits included) and closes its PRs

### MCP Tools
- **ALWAYS use GitHub MCP tools** (`mcp__github__*`) for ALL GitHub operations
  - Exception: Local branches only - use `git checkout -b` instead of `mcp__github__create_branch`
- **ALWAYS use Playwright MCP tools** (`mcp__playwright__*`) for browser testing
  - Test against: `http://localhost:3000` (frontend), `http://localhost:8001` (API)

## Common Issues
1. Use unique keys in v-for (not `index`) - use `sku`, `month`, etc.
2. Validate dates before `.getMonth()` calls
3. Update Pydantic models when changing JSON data structure
4. Inventory filters don't support month (no time dimension)
5. Revenue goals: $800K/month single, $9.6M YTD all months

## File Locations
- Views: `client/src/views/*.vue`
- Components: `client/src/components/*.vue`
- Composables: `client/src/composables/*.js`
- API Client: `client/src/api.js`
- Locales: `client/src/locales/*.js`
- Backend: `server/main.py`, `server/mock_data.py`
- Data: `server/data/*.json`
- Backend tests: `tests/backend/*.py`
- Styles: `client/src/App.vue` (global styles/design tokens), scoped `<style>` per component elsewhere

## Design System
- Colors: Slate/gray (#0f172a, #64748b, #e2e8f0)
- Status: green/blue/yellow/red
- Charts: Custom SVG, CSS Grid for layouts
- No emojis in UI
