# План атомарных задач разработки (`06-tasks.md`)

> Все задачи рассчитаны на **15–30 минут** работы и распределены между 2 разработчиками (**Dev 1 — Backend/Infra**, **Dev 2 — Frontend/UI**) так, чтобы вести разработку параллельно без конфликтов слияния. Напоминание: каждый файл кода — строго до 500 строк.

---

## Phase 0: Bootstrap, Инфраструктура и CI/CD

### `TASK-01` [Dev 1] Инициализация репозитория, линтеров и проверки лимита 500 строк
* **Описание:** Создать структуру папок `backend/` и `frontend/`, настроить `.gitignore`, `.env.example`, конфиг `ruff` в `backend/pyproject.toml` и скрипт проверки длины кодовых файлов.
* **Затрагиваемые файлы:** `.gitignore`, `.env.example`, `backend/pyproject.toml`, `scripts/check_loc.sh`.
* **Критерий проверки (Verification):** Команда `bash scripts/check_loc.sh && ruff check backend/` завершается с кодом `0`.

### `TASK-02` [Dev 2] Инициализация Vue 3 + TypeScript + Pinia + Vuetify 4
* **Описание:** Развернуть Vite-проект во `frontend/`, установить `vuetify`, `pinia`, `vue-router`, `mapbox-gl`, настроить ESLint + Prettier и тему `agroDark` (без Tailwind CSS).
* **Затрагиваемые файлы:** `frontend/package.json`, `frontend/src/main.ts`, `frontend/src/shared/plugins/vuetify.ts`, `frontend/src/shared/types/domain.ts`.
* **Критерий проверки (Verification):** `npm run build` собирает пустой каркас с темой Vuetify 4 без ошибок типизации.

### `TASK-03` [Dev 1] Настройка Docker Compose (Uvicorn + Nginx) и GitHub Actions CI/CD
* **Описание:** Написать `backend/Dockerfile`, `frontend/nginx.conf`, корневой `docker-compose.yml` (1 воркер Uvicorn, лимиты памяти под 2 GB RAM) и пайплайн `.github/workflows/ci-deploy.yml`.
* **Затрагиваемые файлы:** `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `.github/workflows/ci-deploy.yml`.
* **Критерий проверки (Verification):** `docker compose config` валиден, Nginx корректно проксирует `/api/v1/health` на FastAPI.

---

## Phase 1: База данных, Модели и Seed Калужской области

### `TASK-04` [Dev 1] Настройка SQLite WAL, SQLModel таблиц и PIN-авторизации
* **Описание:** Реализовать подключение к SQLite с `PRAGMA journal_mode=WAL`, описать 8 сущностей (`Warehouse`, `Product`, `WarehouseStock`, `Client`, `ClientOrder`, `Truck`, `SimulationRun`, `RouteStop`, `RouteCache`) и middleware/dependency проверки `X-Access-Pin` (пользовательский и системный админ-пин).
* **Затрагиваемые файлы:** `backend/app/core/config.py`, `backend/app/core/database.py`, `backend/app/core/security.py`, `backend/app/models/erp_models.py`, `backend/app/models/run_models.py`, `backend/app/api/v1/auth_router.py`.
* **Критерий проверки (Verification):** `POST /api/v1/auth/verify-pin` возвращает `200 OK` с ролью `admin` для системного пина, `dispatcher` для обычного пина и `401` для неверного.

### `TASK-05` [Dev 1] Seed-данные Калужской области (Обнинск + мульти-склады + B2B-точки) и CRUD ERP
* **Описание:** Написать генератор эталонных данных: 2 склада (*Обнинск-Северный*, *Детчино-Агро*), 3 культуры (*Клубника*, *Томаты*, *Огурцы*), 5 B2B-клиентов в Калужской области (Малоярославец, Боровск, Балабаново, Калуга, Таруса — с типами дорог `asphalt` и `dirt`), 3 разнотипных грузовика (еврофура с рефом, среднетоннажник-вездеход с рефом, тент без рефа). Добавить эндпоинты чтения/обновления ERP и `POST /api/v1/system/reset-demo` (только для админ-пина).
* **Затрагиваемые файлы:** `backend/app/services/seed_kaluga.py`, `backend/app/schemas/erp_schemas.py`, `backend/app/api/v1/erp_router.py`, `backend/app/main.py`.
* **Критерий проверки (Verification):** `GET /api/v1/erp/state` отдаёт полный JSON со складами, остатками, заявками и фурами; `POST /api/v1/system/reset-demo` сбрасывает БД за 50 мс.

---

## Phase 2: Погода, Матрица дорог, Математический солвер и XLSX-экспорт

### `TASK-06` [Dev 1] Интеграция с Open-Meteo API и сервис матрицы расстояний Mapbox
* **Описание:** Реализовать асинхронный клиент погоды по координатам Обнинска с поддержкой ручных пресетов (`normal`, `heatwave_35c`, `heavy_rain`) и сервис `distance_matrix.py`, который кэширует ответы Mapbox Directions/Matrix в таблицу `RouteCache` (с мгновенным фоллбэком на гаверсинус при таймауте 1.5 сек).
* **Затрагиваемые файлы:** `backend/app/services/weather_service.py`, `backend/app/services/distance_matrix.py`.
* **Критерий проверки (Verification):** Запрос матрицы для 7 точек Калужской области отрабатывает быстрее 100 мс при повторном вызове из кэша.

### `TASK-07` [Dev 1] Математическое ядро TCO (`freshness_math.py` + `solver_engine.py`)
* **Описание:** Реализовать формулу сохранности груза $E[\text{Freshness}]$ (учёт $\lambda_p$, температуры, осадков, `has_reefer` и замедления на `dirt`) и солвер минимизации TCO (Вариант Б) на базе `SciPy`/`PuLP` + 2-opt. Учесть запрет проезда тяжёлых фур по грунтовкам, фиксацию уже доставленных точек (`delivered`), graceful fallback в `Unmet Demand` и расчёт дельты «Было / Стало».
* **Затрагиваемые файлы:** `backend/app/services/freshness_math.py`, `backend/app/services/solver_engine.py`, `backend/app/schemas/solver_schemas.py`, `backend/app/api/v1/solver_router.py`.
* **Критерий проверки (Verification):** `POST /api/v1/solver/optimize` считает оптимальный план быстрее 1.5 сек, не назначает еврофуру на грунтовку и корректно возвращает `ComparisonDelta` при передаче `baseline_run_id`.

### `TASK-08` [Dev 1] Потоковый экспорт маршрутных листов в `.xlsx`
* **Описание:** Реализовать генерацию Excel-файла с листами по каждому грузовику, списком точек, весом отгрузки, таймингами, ожидаемой свежестью и сводкой TCO через `openpyxl` в `StreamingResponse`.
* **Затрагиваемые файлы:** `backend/app/services/xlsx_exporter.py`, `backend/app/api/v1/export_router.py`.
* **Критерий проверки (Verification):** `GET /api/v1/export/run/{run_id}/xlsx` отдаёт валидный файл `.xlsx` с заголовком `Content-Disposition: attachment`.

---

## Phase 3: Frontend — Вертикальные срезы (Лендинг, PIN-терминал, ERP, Карта)

### `TASK-09` [Dev 2] Публичный Лендинг и Минималистичный 6-точечный экран PIN-входа
* **Описание:** Сверстать на Vuetify 4 презентационный лендинг (`/`) и экран `/login`: сверху заголовок, по центру 6 точек-индикаторов без отображения цифр, перехват нажатий клавиш `0-9` и `Backspace`, авто-отправка на 6-й цифре, анимация `shake` и мгновенная очистка точек при неверном PIN. Настроить Router Guard.
* **Затрагиваемые файлы:** `frontend/src/sections/landing/LandingPage.vue`, `frontend/src/sections/pin-auth/PinLoginPage.vue`, `frontend/src/sections/pin-auth/PinDotsIndicator.vue`, `frontend/src/sections/pin-auth/useAuthStore.ts`, `frontend/src/router/index.ts`.
* **Критерий проверки (Verification):** Без ввода PIN доступен только `/` и `/login`. Неверный 6-значный PIN вызывает анимацию тряски и очищает точки. Системный PIN открывает флаг `isAdmin`.

### `TASK-10` [Dev 2] Левая панель мини-ERP и управления погодой (Vuetify 4)
* **Описание:** Создать вкладки управления мульти-складами (остатки клубники, томатов, огурцов), B2B-клиентами (объём заказа, инпут закупочной цены, бейдж `Асфальт`/`Грунтовка`, переключатель статуса `Доставлено`) и автопарком (реф, проходимость, тумблер `В строю / Сломана`). В шапку вывести виджет погоды с переключателем стресс-пресетов и кнопку `Hard Reset` (для `isAdmin`).
* **Затрагиваемые файлы:** `frontend/src/sections/erp-dashboard/DashboardLayout.vue`, `frontend/src/sections/erp-dashboard/WarehousesStockTab.vue`, `frontend/src/sections/erp-dashboard/ClientsOrdersTab.vue`, `frontend/src/sections/erp-dashboard/FleetTrucksTab.vue`, `frontend/src/sections/erp-dashboard/WeatherControlBar.vue`, `frontend/src/sections/erp-dashboard/useErpStore.ts`.
* **Критерий проверки (Verification):** Изменение цены клиента, поломка грузовика или отметка «Доставлено» мгновенно обновляют состояние и позволяют запустить пересчёт.

### `TASK-11` [Dev 2] Интерактивная карта Калужской области на Mapbox GL JS
* **Описание:** Инициализировать карту с центром на Обнинске (`[36.61, 55.11]`), отрисовать кастомные маркеры мульти-складов и B2B-покупателей (с цветовой индикацией типа дороги и статуса доставки), а также слои полилиний маршрутов для каждого грузовика с попапами по клику.
* **Затрагиваемые файлы:** `frontend/src/sections/map-routing/KalugaMapCanvas.vue`, `frontend/src/sections/map-routing/useMapboxMarkers.ts`.
* **Критерий проверки (Verification):** После нажатия «Рассчитать поставки» на карте плавно отрисовываются реальные дорожные маршруты между складами и клиентами Калужской области.

---

## Phase 4: Сравнение «Было / Стало», Печать PDF и Полировка под Демо

### `TASK-12` [Dev 2] Панель сводки TCO, модалка «Было / Стало» и печатный PDF-шаблон
* **Описание:** Сверстать панель результатов расчёта (полный TCO, затраты на рейсы, потери от порчи, штрафы за недовоз, ожидаемая прибыль), таблицу сравнения метрик **«Было / Стало»** при сценариях «Что, если», а также компонент `PrintableRouteSheet.vue` со стилями `@media print` для мгновенного экспорта маршрутных листов в PDF и кнопку скачивания `.xlsx`.
* **Затрагиваемые файлы:** `frontend/src/sections/what-if-compare/TcoSummaryPanel.vue`, `frontend/src/sections/what-if-compare/BeforeAfterModal.vue`, `frontend/src/sections/what-if-compare/useSolverStore.ts`, `frontend/src/sections/print-sheet/PrintableRouteSheet.vue`, `frontend/src/shared/styles/print.scss`.
* **Критерий проверки (Verification):** Клик по «Печать PDF» открывает чистый векторный маршрутный лист А4 без интерфейса карты; клик по «Скачать XLSX» сохраняет таблицу маршрутов.

### `TASK-13` [Dev 1 + Dev 2] Сквозное тестирование сценария демо-видео и финал DoD
* **Описание:** Прогнать полный цикл по Definition of Done: вход по 6-значному PIN → показ складов Обнинска и погоды → базовый расчёт → отметка первой точки «Доставлено» + поломка фуры на маршруте + смена цены → мгновенный пересчёт «Было / Стало» → экспорт PDF и XLSX → проверка кнопки `Hard Reset` под системным пином. Проверить соблюдение лимита 500 строк во всех файлах.
* **Затрагиваемые файлы:** Все файлы проекта.
* **Критерий проверки (Verification):** Все 5 пунктов DoD выполняются без единой ошибки в консоли, время отклика солвера менее 2 секунд, `scripts/check_loc.sh` проходит успешно.
