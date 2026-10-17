# Technical Requirements Document (TRD)

## 1. Аппаратные ограничения и Целевой профиль
* **Целевой сервер:** VPS `1 vCPU / 2 GB RAM / 50 GB SSD` (Linux x86_64).
* **Ограничение по памяти:** Запрещено использовать тяжёлые брокеры (Redis, RabbitMQ, Celery), ресурсоёмкие БД (PostgreSQL) и тяжёлые PDF-движки (WeasyPrint, Puppeteer). Приложение запускается напрямую на хосте: FastAPI под `systemd`, статика и reverse proxy через standalone Nginx.
* **Сборка (CI/CD):** Компиляция фронтенда выполняется исключительно на раннере GitHub Actions, чтобы исключить OOM на целевом VPS. CI передаёт готовый `frontend/dist` на сервер; FastAPI работает как `systemd`-сервис с одним Uvicorn worker, Nginx работает как системный сервис. На хосте настраивается swap-файл объёмом 2 GB.

## 2. Технологический стек

### Frontend
* **Core:** Vue 3.5+ (Composition API, `<script setup lang="ts">`), TypeScript 5.6+, Vite 5.4+.
* **State & Routing:** Pinia 2.2+, Vue Router 4.4+.
* **UI Framework:** Vuetify 4 (Material Design компоненты, таблицы, сетка, темы). **Tailwind CSS категорически запрещён.**
* **Картография:** Mapbox GL JS 3.x (`mapbox-gl`).
* **Код-качество:** ESLint 9 + Prettier + `vue-tsc`.

### Backend
* **Core:** Python 3.12, FastAPI 0.115+, Uvicorn 0.30+ (1 worker, async loop).
* **ORM & Database:** SQLModel 0.0.22+ (Pydantic v2 + SQLAlchemy 2.0), SQLite 3 (в режиме `PRAGMA journal_mode=WAL;`).
* **Математический солвер:** `scipy.optimize.milp` (движок HiGHS) / `PuLP` для распределения партий + быстрый эвристический 2-opt маршрутизатор на чистом Python (потребление памяти менее 60 МБ, таймаут решения 1.0 сек).
* **Интеграции и Экспорт:** `httpx` (асинхронные запросы к Open-Meteo и Mapbox с таймаутом 1.5 сек), `openpyxl` (потоковая генерация `.xlsx` в `BytesIO`).
* **Код-качество:** `ruff` (линтер + форматтер).

## 3. Архитектурная схема (Mermaid)

```mermaid
graph TD
    subgraph Client ["Browser (Desktop SPA)"]
        UI["Vue 3 + Vuetify 4 UI"]
        Map["Mapbox GL JS Canvas"]
        Print["Browser Print Engine (@media print -> PDF)"]
    end

    subgraph VPS ["VPS (1 vCPU / 2 GB RAM) — systemd + Nginx"]
        Nginx["Nginx (Static Files + Reverse Proxy /api)"]
        FastAPI["FastAPI + Uvicorn (systemd, 1 worker)"]
        Solver["Bio-Logistics Solver (SciPy HiGHS + 2-Opt)"]
        SQLite[("SQLite WAL (app.db + RouteCache)")]
    end

    subgraph External ["External APIs (Timeout 1.5s)"]
        OpenMeteo["Open-Meteo API (Kaluga Weather)"]
        MapboxAPI["Mapbox Matrix & Directions API"]
    end

    UI -->|HTTPS / X-Access-Pin| Nginx
    Map -->|Vector Tiles| MapboxAPI
    UI -->|window.print()| Print
    Nginx -->|proxy_pass /api/*| FastAPI
    FastAPI <--> SQLite
    FastAPI --> Solver
    FastAPI -->|Async HTTPX| OpenMeteo
    FastAPI -->|Async HTTPX (on cache miss)| MapboxAPI
```

## 4. Внешние API и Стратегия кэширования / фоллбэков
1. **Open-Meteo API (`https://api.open-meteo.com/v1/forecast`):**
   * Запрашивает `current=temperature_2m,precipitation,weather_code` по координатам центра кластера (Обнинск: `55.11, 36.61`).
   * Кэшируется в памяти/БД на 15 минут.
   * Поддерживает принудительный оверрайд из UI (`normal` | `heatwave_35c` | `heavy_rain`), который перекрывает данные API при расчёте сценариев «Что, если».
2. **Mapbox Directions / Matrix API:**
   * При первом расчёте пары координат `(origin -> destination)` запрос сохраняет `distance_km`, `base_duration_min`, реальную дорожную линию и `source = 'mapbox'` в таблицу `RouteCache`. Эта же геометрия без изменений уходит во фронтенд в `RouteResponse.geometry`, поэтому на карте рисуется дорога, а не прямая.
   * Запросы идут конкурентно (семафор 8) под общим дедлайном `EXTERNAL_API_TIMEOUT_SEC`, а непокрытые плечи получают офлайн-оценку с `source = 'fallback'`.
   * **Fallback:** При отсутствии сети, токена или превышении таймаута дистанция мгновенно вычисляется по формуле гаверсинуса с дорожным коэффициентом `1.3`, а геометрия рисуется ломаной с промежуточными узлами.
   * **Апгрейд старого кэша:** записи `fallback` без `mapbox_checked_at` (полученные до появления токена) перезапрашиваются при первом расчёте, поэтому включение `MAPBOX_SECRET_TOKEN` само по себе заменяет прямые линии на дороги без `reset-demo`. Повторные попытки после ошибки троттлятся `MAPBOX_RETRY_INTERVAL_SEC` (15 минут).

## 5. Обработка ошибок и Краевые случаи (Edge Cases)
1. **Авторизация по PIN:** Все эндпоинты `/api/v1/*` (кроме `/api/v1/auth/verify-pin` и `/api/v1/health`) проверяют заголовок `X-Access-Pin`.
   * Пользовательский PIN (например, `202601`) даёт полный доступ к ERP, расчётам и экспорту.
   * Системный админ-PIN (например, `999999`) дополнительно возвращает флаг `is_admin: true` и разрешает вызов `POST /api/v1/system/reset-demo`.
2. **Infeasible-сценарии (дефицит транспорта):** В целевую функцию МИЛП для каждой заявки вводится slack-переменная недовоза $V_{\text{unmet}} \ge 0$ с высоким штрафом $\text{Penalty}_o$. Благодаря этому задача математически **всегда разрешима (Always Feasible)**: при поломке всех фур солвер вернёт валидный ответ с `unmet_kg > 0` и подсветит дефицит в UI.
3. **Вычисления вне Event Loop:** Математический расчёт солвера оборачивается в `await asyncio.to_thread(run_solver, payload)`, чтобы не блокировать асинхронный цикл FastAPI.
4. **Лимиты рейса и свежесть:** солвер ограничивает число остановок на рейс, а после маршрутизации режет точки, не влезающие в смену, возвращая их в недовоз с предупреждением `trip_limit_exceeded`. Свежесть ниже `SOLVER_MIN_STOP_FRESHNESS` не выбрасывает груз из плана (потери уже в TCO), а даёт предупреждение `freshness_risk` по конкретной заявке.

## 6. Переменные окружения (`.env.example`)

```env
# Backend Settings
APP_ENV=production
USER_ACCESS_PIN=202601
ADMIN_ACCESS_PIN=999999
SQLITE_DB_PATH=/opt/agrologistix/data/app.db
EXTERNAL_API_TIMEOUT_SEC=1.5
SOLVER_TIME_LIMIT_SEC=1.0
# План 09-route-consolidation.md: консолидация и лимиты рейсов
SOLVER_CLIENT_SPLIT_PENALTY_RUB=5000
SOLVER_MAX_STOPS_PER_TRIP=5
SOLVER_MAX_TRIP_HOURS=9.0
SOLVER_MIN_STOP_FRESHNESS=0.70

# External Keys
MAPBOX_SECRET_TOKEN=pk.eyJ1IjoiZXhhbXBsZSIsImEiOiJjb...
VITE_MAPBOX_PUBLIC_TOKEN=pk.eyJ1IjoiZXhhbXBsZSIsImEiOiJjb...
VITE_API_BASE_URL=/api/v1
```
