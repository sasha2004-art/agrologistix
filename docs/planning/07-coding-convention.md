# Coding Conventions & AI Agent Rules

> ⚠️ **КРИТИЧЕСКОЕ ПРАВИЛО ДЛЯ AI-АГЕНТОВ И РАЗРАБОТЧИКОВ:**
> 1. **Лимит размера файла:** Любой файл с исходным кодом (`.py`, `.ts`, `.vue`) должен содержать **СТРОГО ДО 500 СТРОК КОДА** (максимум 500 строк). Если файл приближается к 400–450 строкам — немедленно декомпозируй его на подмодули/компоненты. Исключение допускается **только** для файлов документации (`.md`) и таблиц стилей (`.scss`, `.css`).
> 2. **Никакого Tailwind CSS:** На фронтенде используется исключительно **Vuetify 4** и стандартный Scoped SCSS.

## 1. Архитектура директорий проекта

Фронтенд строится по принципу **Вертикальных срезов по разделам/экранам (Vertical Slices)**, бэкенд — по классической **Слоистой архитектуре (Layered Architecture)**.

```text
./
├── .github/
│   └── workflows/
│       └── ci-deploy.yml          # Линтинг, сборка фронта и выкладка по SSH
├── docker-compose.yml             # Nginx + FastAPI (Uvicorn 1 worker)
├── .env.example
├── docs/
│   └── planning/                  # 01-prd.md ... 07-coding-convention.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml             # Конфиг зависимостей и Ruff
│   └── app/
│       ├── main.py                # Инициализация FastAPI, CORS, Lifespan seed
│       ├── core/
│       │   ├── config.py          # Pydantic Settings (.env)
│       │   ├── database.py        # SQLite engine (WAL mode) + get_session
│       │   └── security.py        # Зависимость проверки X-Access-Pin
│       ├── models/                # SQLModel таблицы (до 500 строк)
│       │   ├── erp_models.py      # Warehouse, Product, Stock, Client, Order, Truck
│       │   └── run_models.py      # SimulationRun, RouteStop, RouteCache
│       ├── schemas/               # Pydantic DTO для API запросов/ответов
│       │   ├── erp_schemas.py
│       │   └── solver_schemas.py
│       ├── services/              # Бизнес-логика и интеграции
│       │   ├── seed_kaluga.py     # Начальные данные Обнинска и Калужской обл.
│       │   ├── weather_service.py # Open-Meteo + оверрайды погоды
│       │   ├── distance_matrix.py # Mapbox Matrix API + RouteCache + Haversine fallback
│       │   ├── freshness_math.py  # Расчёт термо-деградации E[Freshness]
│       │   ├── solver_engine.py   # МИЛП (SciPy/PuLP) + 2-opt маршрутизатор
│       │   └── xlsx_exporter.py   # Генерация маршрутных листов в BytesIO
│       └── api/
│           └── v1/
│               ├── auth_router.py
│               ├── erp_router.py
│               ├── solver_router.py
│               └── export_router.py
└── frontend/
    ├── Dockerfile
    ├── nginx.conf                 # Раздача статики + proxy_pass /api -> backend:8000
    ├── package.json
    ├── eslint.config.js
    └── src/
        ├── main.ts                # Инициализация Vue 3, Pinia, Vuetify 4
        ├── App.vue
        ├── router/
        │   └── index.ts           # Маршруты /, /login, /dashboard + Navigation Guard
        ├── shared/                # Переиспользуемая инфраструктура
        │   ├── api/
        │   │   └── httpClient.ts  # Fetch/Axios обёртка с заголовком X-Access-Pin
        │   ├── types/
        │   │   └── domain.ts      # Строгие интерфейсы сущностей и расчётов
        │   ├── plugins/
        │   │   └── vuetify.ts     # Настройка Vuetify 4 и темы agroDark
        │   └── styles/
        │       └── print.scss     # Стили @media print (может быть > 500 строк)
        └── sections/              # Вертикальные срезы по экранам/разделам
            ├── landing/
            │   └── LandingPage.vue
            ├── pin-auth/
            │   ├── PinLoginPage.vue
            │   ├── PinDotsIndicator.vue
            │   └── useAuthStore.ts
            ├── erp-dashboard/
            │   ├── DashboardLayout.vue
            │   ├── WarehousesStockTab.vue
            │   ├── ClientsOrdersTab.vue
            │   ├── FleetTrucksTab.vue
            │   ├── WeatherControlBar.vue
            │   └── useErpStore.ts
            ├── map-routing/
            │   ├── KalugaMapCanvas.vue
            │   └── useMapboxMarkers.ts
            ├── what-if-compare/
            │   ├── TcoSummaryPanel.vue
            │   ├── BeforeAfterModal.vue
            │   └── useSolverStore.ts
            └── print-sheet/
                └── PrintableRouteSheet.vue
```

## 2. Линтеры, Форматтеры и Правила типизации

### Backend (Python 3.12)
* Инструмент: **Ruff** (`ruff check .` и `ruff format .`).
* Обязательная аннотация типов аргументов и возвращаемых значений у всех функций.
* Все эндпоинты возвращают строго типизированные `response_model` из `app/schemas/`.

### Frontend (Vue 3 + TypeScript + Vuetify 4)
* Инструменты: **ESLint + Prettier + `vue-tsc --noEmit`**.
* Запрещено использование типа `any` (`@typescript-eslint/no-explicit-any: "error"`).
* Компоненты пишутся только через `<script setup lang="ts">`.

## 3. Git-гигиена на 2 разработчиков (Zero Merge Conflicts)

### Разделение зон ответственности
* **Разработчик 1 (Backend, Math Solver & DevOps):** Работает внутри `backend/`, `docker-compose.yml`, `.github/workflows/`.
* **Разработчик 2 (Frontend Vertical Slices, Mapbox & Print UI):** Работает внутри `frontend/`.
* **Точка синхронизации:** Контракт DTO в `backend/app/schemas/` и `frontend/src/shared/types/domain.ts`.

### Ветвление и Коммиты
* Основная защищённая ветка: `main` (всегда в рабочем состоянии, триггерит авто-деплой).
* Рабочие ветки именуются по шаблону:
  * `feat/solver-tco-engine`
  * `feat/pin-auth-screen`
  * `fix/dirt-road-constraint`
* **Conventional Commits:** `feat(solver): add dirt road constraint and freshness decay`, `feat(ui): implement 6-dot pin login with shake animation`.
* Перед любым `git push` разработчик обязан прогнать локально линтер (`ruff check` / `npm run lint`) и убедиться, что ни один кодовый файл не превышает **500 строк**.

## 4. CI/CD Pipeline (`.github/workflows/ci-deploy.yml`)
1. При `push` в `main` GitHub Actions запускает джобу `lint-and-build` на `ubuntu-latest`:
   * Проверяет лимит в 500 строк на все файлы `.py`, `.ts`, `.vue`:
     `find backend frontend/src -type f \( -name "*.py" -o -name "*.ts" -o -name "*.vue" \) -exec awk 'END{if (NR > 500) {print FILENAME, NR; exit 1}}' {} +`
   * Прогоняет `ruff check` на бэкенде и `vue-tsc && vite build` на фронтенде.
2. Джоба `deploy`:
   * Копирует собранный `frontend/dist` и код `backend/` по SSH (`appleboy/scp-action` / `rsync`) на целевой VPS.
   * Выполняет `docker compose up -d --build` на сервере (контейнер Nginx подхватывает готовую статику `dist` за 1 секунду без нагрузки на 1 vCPU / 2 GB RAM).
