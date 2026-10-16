# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Frontend: Vue 3.5+ with `<script setup lang="ts">`, TypeScript 5.6+ in strict mode (no `any`), Vite, Pinia, Vue Router 4, Vuetify 4, and Mapbox GL JS (`mapbox-gl`). Use Vuetify components and props plus Scoped SCSS for styling. Tailwind CSS is prohibited.

The frontend is organized as vertical slices: `src/sections/landing`, `pin-auth`, `erp-dashboard`, `map-routing`, `what-if-compare`, `print-sheet`, and `src/shared/`.

Backend: FastAPI + SQLModel + SQLite in `backend/`. Frontend work stays inside `frontend/`. Until backend endpoints are ready, support typed mock mode using shared DTOs; JSON fields use `snake_case`.

## Users

The primary user is an agribusiness holding or distribution-center logistics dispatcher, working at a widescreen desktop monitor to allocate perishable crops from multiple warehouses to B2B buyers and manage delivery routes.

The operating geography is Kaluga Oblast, centered on Obninsk. The planned domain includes multiple warehouses (for example, Obninsk-Severny and Detchino-Agro), three crops (strawberries, tomatoes, cucumbers), and five B2B buyers.

## Product Purpose

AgroLogistix is a B2B bio-logistics optimization platform with built-in mini-ERP. It distributes perishable harvest from warehouses to B2B customers by optimizing routes for a mixed vehicle fleet, and recalculates plans when operational stress events occur. Success means producing an operationally and financially viable delivery plan that dispatchers can revise as conditions change.

## Positioning

The differentiating mechanism is a unified, real-time Total Cost of Ownership (TCO) calculation that combines trip economics and shortfall penalties (`unmet_kg`), expected in-transit freshness (`E[Freshness]`) affected by weather and refrigeration (`has_reefer`), and vehicle access constraints based on customer-site road surface (`asphalt` or `dirt`). A heavy European truck cannot use a dirt road.

During what-if recalculation, already delivered orders are fixed by `order_id` with `delivery_status = 'delivered'`. Dispatchers can compare the previous and proposed plan with “Was / Will be” metrics.

## Operating Context

The dispatcher workflow covers warehouses and orders, fleet, route planning and TCO, weather presets, and what-if comparison. Stress events include a vehicle breaking down on a route, a buyer changing a purchase price, and severe weather changes.

The planned public landing route is `/`, linking to the dispatcher PIN login at `/login`. The operations workspace is `/dashboard`.

The dashboard has a 56px top bar with region, weather preset control (`normal`, `heatwave_35c`, `heavy_rain`), “Was / Will be” comparison, and an admin-only Hard Reset. Its 35%-width left panel (minimum 440px) has tabs for Warehouses and Orders, Fleet, and Routes and TCO, plus a bottom-pinned “Calculate deliveries” action. The 65%-width right area is a Mapbox map centered on Obninsk at `[36.61, 55.11]`, with warehouse and customer markers, road-surface and delivery-status indicators, colored route polylines, and a local fallback when the network is unavailable.

PIN login uses a six-dot indicator; entered digits are never displayed. Verification runs automatically after the sixth digit via `X-Access-Pin` on `POST /api/v1/auth/verify-pin`. On error, dots turn red, the input shakes for 300ms, and the field clears automatically. Roles are `dispatcher` and system `admin`; admin sees a Hard Reset Demo control.

Route sheets can be printed as vector A4 using browser `@media print` and `window.print()`, hiding the map and application UI. XLSX export downloads a prepared backend file from `GET /api/v1/export/run/{run_id}/xlsx`.

What-if changes (order delivery status, vehicle `broken` state, price, or weather preset) must first be persisted on the server using `PATCH /api/v1/erp/*` or `POST /api/v1/weather/override`. Only then call `POST /api/v1/solver/optimize` with `{ "mode": "what_if", "baseline_run_id": <id> }`. The server is the single source of truth.

## Capabilities and Constraints

- Desktop-first Web SPA; the main application workspace is designed for a 100vh widescreen viewport without whole-page vertical scrolling.
- Every code file with extension `.ts`, `.vue`, or `.py` must be strictly under 500 lines (maximum 499); CI checks this limit. Documentation and style files such as `.scss`, `.css`, and `.md` are exempt.
- Use typed DTOs and strict TypeScript; do not use `any`.
- Preserve the API's `snake_case` JSON field names.
- While endpoints are under development, frontend features must support typed mock mode using the shared DTOs.
- Target deployment infrastructure is limited to 1 vCPU, 2 GB RAM, and 50 GB SSD. Frontend static assets and `/api` reverse proxy are served through Nginx in Docker Compose.

## Brand Commitments

The product name is AgroLogistix. The confirmed default interface theme is `agroDark`: background `#0F172A`, surface `#1E293B`, primary `#10B981`, secondary `#38BDF8`, warning `#F59E0B`, error `#EF4444`, and success `#22C55E`. Provide a light print presentation for exports. Use Inter or Roboto for UI and JetBrains Mono for TCO, weight, and timing figures.

## Evidence on Hand

The product scope, workflows, routes, API contracts, domain entities, UI constraints, and technology choices in this record are confirmed in the project architecture supplied by the user. No live backend endpoint readiness, real operational dataset, customer testimonial, or production deployment evidence has been established; do not fabricate these.

## Product Principles

- Optimize the delivery plan against financial, freshness, weather, and vehicle-access realities together.
- Treat server-persisted operational state as authoritative before optimization.
- Preserve completed deliveries during replanning and make plan changes comparable.
- Keep dispatcher workflows usable in a dense desktop operations context and provide a local map fallback.
- Keep frontend contracts typed and aligned with backend DTOs.
