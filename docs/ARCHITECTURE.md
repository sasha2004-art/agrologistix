# AgroLogistix — техническая документация сервиса

> Единый источник правды по внутреннему устройству сервиса: архитектура, данные,
> API, математическое ядро, фронтенд, тесты, CI/CD и деплой.
> Запуск и развёртывание — в `docs/LAUNCH.md`, ручные проверки с контрольными
> числами — в `docs/MANUAL-TESTS.md`.
> **При изменении кода, формул, DTO или настроек обновляйте этот файл в том же PR.**

---

## 1. Что делает сервис

AgroLogistix — B2B-платформа оперативного планирования поставок скоропортящегося
урожая (клубника, томаты, огурцы) с мульти-складов агрохолдинга по B2B-покупателям
Калужской области. Логист-диспетчер:

1. входит по 6-значному PIN-коду;
2. правит мини-ERP: остатки складов, заявки (цена, статус доставки), автопарк
   (в строю / не в работе), погодный пресет;
3. нажимает «Рассчитать поставки»;
4. получает план: рейсы по машинам с порядком остановок, полилинии на карте,
   свежесть груза в каждой точке, финансовые метрики TCO (доставка и потери),
   процент потерянного урожая и долю недовоза, предупреждения; штрафов
   в интерфейсе нет — недовоз измеряется килограммами и процентами;
5. выгружает маршрутные листы в XLSX или печатает PDF через браузер.

Расчёт всегда строится заново по актуальному состоянию ERP и погоды: у запроса нет
режимов и сценариев, а изменения логиста сначала сохраняются через `PATCH`, после
чего план помечается устаревшим и пересчитывается кнопкой.

**Роли:** `dispatcher` (полный доступ к ERP, расчёту и экспорту) и `admin`
(дополнительно `POST /system/reset-demo`). Авторизация — заголовок `X-Access-Pin`.

---

## 2. Архитектура

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
        Solver["Bio-Logistics Solver (SciPy HiGHS + 2-opt + local search)"]
        SQLite[("SQLite WAL (app.db: ERP, runs, RouteCache)")]
    end

    subgraph External ["External APIs (timeout 1.5 s)"]
        OpenMeteo["Open-Meteo API (Kaluga weather)"]
        MapboxAPI["Mapbox Directions API"]
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

**Стек.**

| Слой | Технологии |
| :--- | :--- |
| Frontend | Vue 3.5 (Composition API, `<script setup lang="ts">`), TypeScript 5.6, Vite 5.4, Pinia 2.2, Vue Router 4.4, Vuetify 4, Mapbox GL JS 3.x, ESLint 9 + Prettier + `vue-tsc` |
| Backend | Python 3.12, FastAPI 0.115+, Uvicorn (1 worker), SQLModel 0.0.22+ (Pydantic v2 + SQLAlchemy 2.0), SQLite в режиме WAL, SciPy `optimize.milp` (HiGHS), NumPy, httpx, openpyxl, ruff |
| Инфраструктура | standalone Nginx, `systemd`, GitHub Actions (сборка фронта на раннере), Let's Encrypt / certbot |

**Жёсткие ограничения окружения.** Целевой сервер — `1 vCPU / 2 GB RAM`: запрещены
Redis/RabbitMQ/Celery/PostgreSQL и тяжёлые PDF-движки (WeasyPrint, Puppeteer). PDF —
только браузерная печать; XLSX генерируется `openpyxl` в `BytesIO`. Внешние API
имеют таймаут 1.5 с и локальные fallback/cache, чтобы демо не зависело от сети.
Swap-файл 2 GB настраивается на хосте (см. `docs/LAUNCH.md`).

**Сквозной поток данных.**

1. SPA читает `GET /api/v1/erp/state` и `GET /api/v1/weather/current`.
2. Логист правит данные — `PATCH /erp/orders|trucks|stocks`, `POST /weather/override`.
3. `POST /api/v1/solver/optimize` читает актуальное состояние из SQLite, строит
   матрицу расстояний (кэш `route_cache` → Mapbox → haversine-fallback), прогоняет
   солвер, сохраняет `simulation_run` + `route_stop` и возвращает JSON.
4. SPA рисует рейсы на Mapbox, показывает TCO, свежесть и предупреждения.
5. `GET /api/v1/export/run/{id}/xlsx` отдаёт маршрутный лист по сохранённому прогону.

---

## 3. Структура репозитория

```text
./
├── .github/workflows/ci-deploy.yml   # lint/test/build + deploy в main
├── deploy/                            # systemd, Nginx, rsync-деплой, HTTPS
├── docs/
│   ├── ARCHITECTURE.md                # этот файл
│   ├── LAUNCH.md                      # генерируется из launch.config.json
│   ├── launch.config.json             # источник инструкции запуска
│   └── MANUAL-TESTS.md                # ручные проверки
├── scripts/
│   ├── check_loc.sh                   # лимит 500 строк на кодовый файл
│   └── generate_launch_doc.py         # генерация LAUNCH.md
├── backend/
│   ├── pyproject.toml                 # зависимости и конфиг ruff
│   └── app/
│       ├── main.py                    # FastAPI, CORS, lifespan seed, роутеры
│       ├── core/                      # config, database (WAL+миграции), security, errors
│       ├── models/                    # erp_models.py, run_models.py (SQLModel)
│       ├── schemas/                   # Pydantic DTO запросов/ответов
│       ├── services/                  # бизнес-логика (см. §6–§9)
│       └── api/v1/                    # auth, erp, weather, solver, export, health
└── frontend/
    └── src/
        ├── router/index.ts            # /, /login, /dashboard + guard
        ├── sections/                  # вертикальные срезы по экранам
        │   ├── landing/
        │   ├── pin-auth/
        │   ├── erp-dashboard/
        │   └── map-routing/
        └── shared/                    # api, types, plugins, styles, utils, components
```

---

## 4. Конфигурация

Настройки читаются Pydantic Settings из переменных окружения и `.env`
(шаблон — `.env.example`). Секреты PIN и токенов — `SecretStr` и не попадают в
`repr`/логи.

| Переменная | Дефолт | Назначение |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | `production` требует явных PIN и предупреждает о дефолтных |
| `USER_ACCESS_PIN` | `202601` | PIN диспетчера (ровно 6 цифр) |
| `ADMIN_ACCESS_PIN` | `999999` | PIN администратора (ровно 6 цифр, отличается от пользовательского) |
| `SQLITE_DB_PATH` | `./data/app.db` | Путь к файлу SQLite |
| `EXTERNAL_API_TIMEOUT_SEC` | `1.5` | Таймаут Open-Meteo и Mapbox, общий дедлайн матрицы |
| `SOLVER_TIME_LIMIT_SEC` | `1.0` | Лимит HiGHS; половина уходит на каждую из двух MILP-попыток |
| `SOLVER_CLIENT_SPLIT_PENALTY_RUB` | `5000` | Внутренний вес дробления клиента между рейсами (мягкий режим) |
| `SOLVER_MAX_STOPS_PER_TRIP` | `5` | Максимум остановок в рейсе |
| `SOLVER_MAX_TRIP_HOURS` | `9.0` | Максимальная длительность рейса (смена) |
| `SOLVER_MIN_STOP_FRESHNESS` | `0.70` | Порог свежести: ниже — предупреждение `freshness_risk` |
| `SOLVER_IMPROVE_TIME_BUDGET_SEC` | `0.7` | Бюджет локального поиска по фактическому TCO |
| `SOLVER_IMPROVE_MAX_EVALUATIONS` | `400` | Лимит кандидатов локального поиска |
| `WEATHER_LATITUDE` | `55.11` | Центр метеосводки (Обнинск) |
| `WEATHER_LONGITUDE` | `36.61` | Центр метеосводки (Обнинск) |
| `WEATHER_CACHE_TTL_SEC` | `900` | TTL кэша живой погоды в памяти |
| `MAPBOX_SECRET_TOKEN` | пусто | Серверные запросы к Mapbox Directions; пусто → haversine-fallback |
| `VITE_MAPBOX_PUBLIC_TOKEN` | пусто | Публичный токен карты, встраивается в бандл на этапе сборки |
| `VITE_API_BASE_URL` | `/api/v1` | База API для фронтенда |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:4173` | Разрешённые origin'ы |
| `VITE_DEMO_USER_PIN` / `VITE_DEMO_ADMIN_PIN` | `202601` / `999999` | Dev-mock PIN, только при недоступном backend |

---

## 5. Модель данных (SQLite + SQLModel)

База создаётся при старте (`SQLModel.metadata.create_all`) и дополняется
идемпотентными миграциями `_SQLITE_MIGRATIONS` в `app/core/database.py`:
`simulation_run.total_shipped_kg`, `simulation_run.total_unmet_kg`,
`client_order.delivered_kg`, `route_cache.source`, `route_cache.mapbox_checked_at`.
SQLite работает в режиме `PRAGMA journal_mode=WAL`.

| Таблица | Назначение и ключевые поля |
| :--- | :--- |
| `warehouse` | Склады: `name`, `lat`, `lon`, `address`, `is_active`. Неактивный склад исключается из плана и расчёта стока |
| `product` | Культуры: `code` (unique), `base_spoilage_rate` ($\lambda_p$), `optimal_temp_c`, `base_cost_rub` (справочная себестоимость, в TCO не участвует) |
| `warehouse_stock` | Партия: `warehouse_id` + `product_id` (unique), `available_kg ≥ 0`, `initial_freshness ∈ [0.5, 1]` |
| `client` | B2B-точка: `lat`, `lon`, `road_type ∈ {asphalt, dirt}`, `address` |
| `client_order` | Заявка: `requested_kg > 0`, `purchase_price_rub > 0`, `unmet_penalty_rub ≥ 0`, `delivered_kg ≥ 0`, `delivery_status ∈ {pending, in_progress, delivered}` |
| `truck` | Машина: `plate_number` (unique), `warehouse_id`, `capacity_kg`, `cruise_speed_kmh`, `cost_per_km_rub`, `fixed_trip_cost_rub`, `has_reefer`, `has_insulation` (изотермический кузов), `can_use_dirt`, `status ∈ {active, broken}` |
| `simulation_run` | Неизменяемый слепок расчёта: время, погодный режим, температура/осадки и все метрики TCO |
| `route_stop` | Остановка прогона: заявка, машина, склад, клиент, продукт, порядок, кг, плечо, ETA, свежесть, стоимость плеча, `stop_status ∈ {planned, delivered}` |
| `delivered_order_stock` | Журнал списания: `order_id`, `stock_id`, `shipped_kg` — нужен для отката доставки |
| `route_cache` | Кэш дорожных плеч: `pair_key` (PK), `distance_km`, `base_duration_min`, полилиния `(lat, lon)`, `source ∈ {mapbox, fallback}`, `mapbox_checked_at` |
| `fixed_assignment` | Зафиксированный маршрут заявки «В работе»: `order_id` (unique), `truck_id`, `warehouse_id`, `client_id`, `product_id`, `shipped_kg`, `distance_km`, `duration_min`, `expected_freshness`, `trip_cost_rub`, полилиния `geojson_geometry`, `created_at` |
| `weather_override` | Singleton-строка с активным погодным пресетом |

**Seed Калужской области** (`services/seed_kaluga.py`, идемпотентный при старте):

* склады: «Хаб Обнинск» (55.0968, 36.6103), «Склад Детчино» (54.8083, 36.2333);
* культуры: клубника (`λ = 0.08`, +4 °C), томаты (`λ = 0.035`, +10 °C), огурцы (`λ = 0.02`, +10 °C);
* партии (кг / начальная свежесть): Обнинск 4500/0.97, 11 000/0.93,
  7000/0.90; Детчино 2500/0.82, 6000/0.95, 3500/0.78 — остатки уровня
  хаба (тонны на культуру), а не размера заявки;
* 5 клиентов: ВкусВилл (asphalt), Агро-Рынок (asphalt),
  Кооператив Боровск (**dirt**), Пятёрочка (asphalt), Эко-база (**dirt**);
* 9 заявок общим спросом **4 175 кг** — дневная поставка на точку:
  400 клубники + 1200 томатов ВкусВилл, 600 томатов + 350 огурцов Агро-Рынок,
  150 клубники + 250 огурцов Кооператив, 750 томатов + 175 клубники Пятёрочка,
  300 огурцов Эко-база;
* автопарк: Volvo FH16 (10 000 кг, 75 км/ч, 29 ₽/км, 4250 ₽, реф,
  без грунта, Обнинск), ГАЗон NEXT (3000 кг, 62 км/ч, 16 ₽/км, 1900 ₽,
  реф, грунт, Обнинск), КАМАЗ Компас (5000 кг, 70 км/ч, 20 ₽/км, 2300 ₽,
  без рефа, **утеплённый кузов**, грунт, Детчино).

Полный список значений — константы `WAREHOUSE_SEED`, `PRODUCT_SEED`, `STOCK_SEED`,
`CLIENT_SEED`, `ORDER_SEED`, `TRUCK_SEED`.

---

## 6. Математическое ядро

Расчёт — чистая функция `run_solver(SolverInput) -> SolverOutcome`
(`services/solver_engine.py`); CPU-часть уходит из event loop через
`asyncio.to_thread` (`solve_async`). Вход собирает `services/solver_input.py` из
SQLite, выход в DTO конвертирует `services/solver_mapper.py`.

### 6.1 Свежесть груза

$$
E[\text{Freshness}] = \operatorname{clamp01}\Big(\text{initial\_freshness} \cdot e^{-\lambda_p \cdot t_{\text{actual}} \cdot k_{\text{temp}}}\Big)
$$

* $\lambda_p$ — `product.base_spoilage_rate`, базовый темп порчи за час:
  клубника `0.08`, томаты `0.035`, огурцы `0.02`;
* `initial_freshness` — свежесть партии на складе (0.5…1.0);

$$
t_{\text{actual}} = \frac{\text{distance\_km}}{\text{cruise\_speed\_kmh}} \cdot k_{\text{surface}} \cdot k_{\text{rain}}
$$

* $k_{\text{surface}} = 1.35$ для грунтового подъезда (`dirt`), $1.0$ для асфальта;
* $k_{\text{rain}} = 1 + 0.3 \cdot \min\big(1,\ \text{precipitation\_mm} / 10\big)$ —
  линейный рост до +30 % при 10 мм/ч и выше;

$$
k_{\text{temp}} =
\begin{cases}
1.0, & \text{есть рефрижератор или } T \le T_{\text{limit}} \\
e^{\,0.08 \cdot (T - T_{\text{limit}})}, & \text{без рефрижератора и } T > T_{\text{limit}}
\end{cases}
$$

где $T_{\text{limit}} = +22\,^\circ\text{C}$ для обычного кузова и
$T_{\text{limit}} = +28\,^\circ\text{C}$ для утеплённого (изотермического):
изоляция даёт бонус $+6\,^\circ\text{C}$ за счёт тепловой инерции кузова.
Рефрижератор порога не имеет — он держит $k_{\text{temp}} = 1.0$.

Коэффициент `0.08` — Q10-подобный: $e^{0.08 \cdot 10} \approx 2.23$, то есть порча
примерно удваивается на каждые +10 °C выше порога. Потери в рублях:

$$
\text{spoilage\_loss} = \text{shipped\_kg} \cdot \big(1 - E[\text{Freshness}]\big) \cdot \text{price\_per\_kg}
$$

Время накапливается по маршруту: каждый следующий стоп считается по суммарному
времени от склада, поэтому свежесть монотонно убывает по ходу рейса.

### 6.2 Целевая функция и метрики

Внутри оптимизатора недовоз имеет технический вес `penalty_per_kg`: без него
slack-переменная была бы бесплатной, и план мог бы вообще не везти груз.

$$
\min Z_{\text{internal}} = \underbrace{\sum_{r \in \text{рейсы}} C_{\text{trip}}(r)}_{C_{\text{trip}}}
+ \underbrace{\sum_{s \in \text{стопы}} \text{shipped\_kg}_s \cdot (1 - E[\text{Freshness}]_s) \cdot \text{price}_p}_{\text{потери от порчи}}
+ \underbrace{\sum_{o \in \text{заявки}} \text{unmet\_kg}_o \cdot \text{penalty}_o}_{\text{внутренний вес недовоза}}
$$

`penalty_per_kg` — служебный параметр MILP: в публичный DTO он не отдаётся и в
интерфейсе не показывается (остаётся телеметрией `simulation_run`). Публичные
метрики считают **только фактически отгруженный груз**:

$$
\text{total\_tco} = C_{\text{trip}} + \text{потери от порчи}
$$

Стоимость рейса, как её считает `build_route`:

$$
C_{\text{trip}}(r) = \text{fixed\_trip\_cost} + \sum_{\text{плечи } l} \text{distance}_l \cdot \text{cost\_per\_km}
$$

Фиксированная стоимость списывается на **первый стоп** рейса и целиком входит в
`trip_leg_cost_rub` этого стопа.

Итоговые метрики (`_collect_metrics`):

| Метрика | Формула |
| :--- | :--- |
| `total_tco_rub` | $C_{\text{trip}} + \text{потери}$ (без внутреннего веса недовоза) |
| `expected_net_profit_rub` | $\sum \text{shipped\_kg} \cdot \text{price} - \text{total\_tco}$ |
| `avg_freshness_pct` | $\dfrac{\sum \text{shipped\_kg} \cdot \text{freshness}}{\sum \text{shipped\_kg}} \cdot 100$ |
| `spoilage_pct` | $100 - \text{avg\_freshness\_pct}$; $0$, если отгрузки не было |
| `unmet_pct` | $\dfrac{\text{unmet\_kg}}{\sum \text{requested\_kg}} \cdot 100$ |
| `shipped_kg` / `unmet_kg` | сумма отгруженных кг / сумма slack-переменных недовоза |
| `total_trips` | число использованных машин (= число маршрутов) |
| `avg_load_factor_pct` | $\dfrac{\text{shipped\_kg}}{\sum \text{capacity использованных машин}} \cdot 100$ |
| `split_clients` | число клиентов, чьи заявки развезены более чем одной машиной |

Внутренняя телеметрия `PlannedMetrics.total_unmet_penalty_rub` (вес недовоза × кг)
пишется в `simulation_run`, но в ответе API отсутствует.

### 6.3 Грузовая аллокация (MILP)

Решается через `scipy.optimize.milp` (HiGHS). Переменные:

* $x_{k,o} \ge 0$ — килограммы заявки $o$, которые везёт машина $k$;
* $u_o \ge 0$ — недовоз заявки (slack с внутренним весом `unmet_penalty_rub`;
  в публичные метрики не входит);
* $y_k \in \{0,1\}$ — машина используется (платит `fixed_trip_cost_rub`);
* $z_{k,c} \in \{0,1\}$ — машина $k$ обслуживает клиента $c$;
* $s_c \ge 0$ — slack дробления клиента (цена `SOLVER_CLIENT_SPLIT_PENALTY_RUB`);
* $w_{k,o} \in \{0,1\}$ — машина $k$ реально везёт заявку $o$ (для лимита остановок).

Ограничения:

$$
\begin{aligned}
&\sum_k x_{k,o} + u_o = \text{requested}_o && \text{(покрытие заявки)}\\
&\sum_o x_{k,o} \le \text{capacity}_k \cdot y_k && \text{(вместимость)}\\
&\sum_{k \text{ базы } w} x_{k,o:p} \le \text{stock}_{w,p} && \text{(общий сток склада и продукта)}\\
&x_{k,o} = 0, \text{ если } \neg\,\text{truck\_can\_serve\_order}(k,o) && \text{(грунт / нет стока)}\\
&x_{k,o} \le \text{requested}_o \cdot z_{k,c(o)} && \text{(связка с клиентом)}\\
&\sum_k z_{k,c} - s_c = 1 && \text{(строгий режим: } s_c \equiv 0\text{)}\\
&\sum_o w_{k,o} \le \text{max\_stops\_per\_trip} && \text{(лимит остановок)}\\
&x_{k,o} \le \text{requested}_o \cdot w_{k,o} && \text{(груз только на посещаемую точку)}
\end{aligned}
$$

Целевая функция:

$$
\sum_{k,o} \text{unit\_cost}_{k,o} \cdot x_{k,o}
+ \sum_o \text{penalty}_o \cdot u_o
+ \sum_k \text{fixed}_k \cdot y_k
+ \sum_c \text{split\_penalty} \cdot s_c
$$

где прокси-стоимость килограмма
$\text{unit\_cost} = \text{spoilage\_per\_kg} + \dfrac{\text{cost\_per\_km} \cdot \text{distance}(\text{склад} \to \text{клиент})}{\text{requested\_kg}}$.

**Алгоритм выбора.** MILP запускается дважды — со строгой группировкой клиента
(«магазин — один рейс») и с мягким весом дробления клиента, по половине
`SOLVER_TIME_LIMIT_SEC` на попытку. Побеждает вариант с ключом
`(unmet_kg, режим, objective)`: сначала минимизируется недовоз, затем предпочитается
строгая группировка. При ошибке HiGHS или истечении лимита включается жадный
fallback: заявки сортируются по ценности клиента (`penalty · kg`), грузятся на
машину, которая уже везёт этого клиента, затем на ближайшую к точке. Итог:
задача **всегда разрешима** — при поломке всего автопарка вернётся валидный ответ с
`unmet_kg > 0`, а не 500.

### 6.4 Маршрутизация и ETA

`services/solver_routing.py` строит маршрут для каждой загруженной машины:

1. **nearest neighbour** — начальный порядок объезда от склада;
2. **2-opt** (до 20 проходов) — итеративное улучшение открытого маршрута;
3. по каждому плечу накапливаются километры и часы
   ($t = \frac{km}{v} \cdot k_{\text{surface}} \cdot k_{\text{rain}}$), считается
   свежесть по накопленному времени и стоимость плеча
   ($km \cdot \text{cost\_per\_km}$, плюс фикс на первом стопе);
4. геометрия плеч склеивается в одну полилинию рейса без дублей точек.

Матрица расстояний ищется в `LegIndex` по округлённым до 5 знаков координатам; для
неизвестных пар мгновенно считается haversine-fallback.

### 6.5 Зафиксированные рейсы

Заявки, взятые «В работе», имеют запись в `fixed_assignment` — выбранную логистом
машину, склад, метрики и полилинию. Движок получает их в `SolverInput.fixed_routes`:

* заявка фиксированного рейса не участвует в MILP и не попадает в недовоз;
* машина фиксации исключается из активного парка, поэтому одна и та же машина
  не везёт два рейса в одном плане;
* готовый рейс добавляется в `outcome.routes` после лимитов смены и остановок
  (он уже утверждён), а его груз, выручка и потери входят в метрики прогона;
* при возврате заявки в «В плане» или закрытии она удаляется из `fixed_assignment`
  и снова участвует в расчёте.

### 6.6 Мультистоп и консолидация рейсов

MILP-черновик считается по прокси-стоимостям, поэтому после него запускается
`services/solver_improve.py` — детерминированный локальный поиск **по фактическому
TCO** (маршруты перестраиваются, метрики пересчитываются). Операторы по убыванию
отдачи:

| Оператор | Действие |
| :--- | :--- |
| `merge` | перенести все заявки рейса A в рейс B и освободить A |
| `relocate_client` | собрать все заявки одного клиента в один рейс |
| `move` | перенести одну заявку в другой рейс |
| `swap` | обменять заявки между рейсами |

Кандидат принимается только если он **feasible** (вместимость, общий сток склада,
грунт, лимит остановок), укладывается в смену (`within_shift`) и не увеличивает
число «раздробленных» визитов, а его TCO строго меньше текущего на `0.01 ₽`.
Поиск — first-improvement с рестартом от улучшенного плана; бюджет —
`SOLVER_IMPROVE_TIME_BUDGET_SEC` / `SOLVER_IMPROVE_MAX_EVALUATIONS`. Если улучшений
нет, возвращается исходный MILP-план. Метод аллокации (`milp`, `milp+split`,
`greedy`, `…+improved`) остаётся внутренним (логируется), в API не отдаётся.

Цель консолидации — правило логиста: **если одна машина может за один выезд
привезти товар в несколько магазинов, едет одна машина**; вторая подключается
только при нехватке вместимости, стока, грунта или рефрижератора.

### 6.6 Лимиты рейса

После роутинга `services/solver_limits.py` проверяет рейсы по фактическим ETA:

* число остановок $> `SOLVER_MAX_STOPS_PER_TRIP`$ — хвост рейса снимается;
* ETA любой остановки $> `SOLVER_MAX_TRIP_HOURS`$ — поздние точки снимаются;
* свежесть ниже `SOLVER_MIN_STOP_FRESHNESS` **не снимает** стоп: груз везётся,
  потери уже в TCO, а логист получает предупреждение `freshness_risk`.

Снятые килограммы возвращаются в недовоз, рейс пересчитывается по оставшимся
остановкам, в предупреждения попадает `trip_limit_exceeded`.

### 6.7 Предупреждения

| Код | Severity | Условие |
| :--- | :--- | :--- |
| `broken_trucks_excluded` | info | часть машин не в работе (`broken`) исключена |
| `no_active_trucks` | error | активных машин нет, весь спрос уходит в недовоз |
| `unmet_demand` | warning / error | есть недовоз; error при доле ≥ 50 % спроса |
| `dirt_unreachable` | error | грунтовая заявка, а машины с `can_use_dirt` нет (по каждой заявке) |
| `heat_without_reefer` | warning | $T$ выше порога кузова ($+22°$, с утеплением $+28°$) и рейс без рефрижератора |
| `stock_shortage` | warning | суммарный сток продукта меньше суммарного спроса |
| `freshness_risk` | warning | свежесть остановки ниже порога `SOLVER_MIN_STOP_FRESHNESS` |
| `trip_limit_exceeded` | warning | сработал лимит остановок или смены |

---

## 7. Погода (`services/weather_service.py`)

* Режимы: `normal` (в UI — «Фактическая погода», данные Open-Meteo),
  `heatwave_35c` (+35 °C, 0 мм, «Симуляция: жара») и `heavy_rain`
  (+16 °C, 12 мм, WMO 65, «Симуляция: сильный дождь»). Симуляции —
  демонстрационные: они меняют расчёт, но не являются прогнозом, и в интерфейсе
  это подписано явно.
* `normal` тянет Open-Meteo
  (`current=temperature_2m,precipitation,weather_code`, timezone UTC) по
  координатам `WEATHER_LATITUDE/WEATHER_LONGITUDE`, таймаут
  `EXTERNAL_API_TIMEOUT_SEC`.
* Ответ кэшируется в памяти процесса на `WEATHER_CACHE_TTL_SEC` (15 минут).
* Ошибка сети/парсинга → fallback `+20 °C`, 0 мм, код 1; эндпоинт всё равно
  отвечает `200`.
* Активный пресет хранится в SQLite (`weather_override`), поэтому переживает
  рестарт и сбрасывается вместе с демо-данными. `POST /weather/override`
  переключает режим, `GET /weather/current` возвращает актуальный снимок.

---

## 8. Матрица расстояний и кэш (`services/distance_matrix.py`)

* Основной источник — Mapbox Directions
  (`geometries=geojson`, `overview=full`), конкурентные запросы через семафор 8
  и общий дедлайн `asyncio.timeout(EXTERNAL_API_TIMEOUT_SEC)`.
* Кэш — таблица `route_cache` с ключом `pair_key` (координаты, округлённые до
  5 знаков ≈ 1.1 м). Записи со `source = 'mapbox'` используются как есть.
* **Fallback:** расстояние по гаверсинусу с радиусом Земли `R = 6371.0088 км`,
  умноженное на дорожный коэффициент `1.3`; базовое время — при 60 км/ч; геометрия
  — прямая ломаная из 8 сегментов. Позже солвер пересчитывает время под конкретную
  машину, тип дороги и осадки.
* **Апгрейд и троттлинг:** если токен появился позже, старые `fallback`-записи
  без `mapbox_checked_at` (или с давностью ≥ `MAPBOX_RETRY_INTERVAL_SEC = 900 c`)
  перезапрашиваются; неудачные попытки не повторяются на каждом пересчёте.

---

## 9. API

Префикс — `/api/v1`. Формат ошибок:

```json
{"code": "validation_error", "detail": "Request validation failed", "fields": {"...": ["..."]}}
```

Коды: `bad_request` (400), `unauthorized` (401), `forbidden` (403),
`not_found` (404), `conflict` (409), `validation_error` (422),
`request_error` / `not_implemented` / `not_found` (по статусу).

| Метод и путь | Авторизация | Назначение |
| :--- | :--- | :--- |
| `GET /health` | без PIN | Проверка доступности API |
| `POST /auth/verify-pin` | PIN в заголовке | Проверка PIN, возврат роли и `is_admin` |
| `GET /auth/session` | `X-Access-Pin` | Текущая сессия |
| `GET /erp/state` | `X-Access-Pin` | Полное состояние ERP |
| `PATCH /erp/orders/{id}` | `X-Access-Pin` | Цена и/или статус доставки заявки |
| `POST /erp/orders/{id}/assign` | `X-Access-Pin` | Подбор и фиксация оптимальной машины и маршрута заявки |
| `PATCH /erp/trucks/{id}` | `X-Access-Pin` | `active` / `broken` |
| `PATCH /erp/stocks/{id}` | `X-Access-Pin` | Остаток партии |
| `GET /weather/current` | `X-Access-Pin` | Погода и активный режим |
| `POST /weather/override` | `X-Access-Pin` | Сменить пресет погоды |
| `POST /solver/optimize` | `X-Access-Pin` | Пересчитать план по актуальному состоянию |
| `GET /export/run/{run_id}/xlsx` | `X-Access-Pin` | XLSX-маршрутный лист сохранённого прогона |
| `POST /system/reset-demo` | `X-Access-Pin` + admin | Полный сброс демо-данных |

**Авторизация.** PIN — ровно 6 ASCII-цифр; сравнение — `hmac.compare_digest`.
Все защищённые эндпоинты зависят от `AccessContext` (`get_access_context`),
админские — от `AdminContext` (`require_admin`). Ошибки авторизации отдают
`WWW-Authenticate: X-Access-Pin`.

**Ключевые DTO** (`app/schemas`):

```text
SolverRequest:  {}                      # режимов и полей нет

SolverResponse:
  run_id: int
  routes: Route[]                       # truck_id, truck_name, warehouse_id,
                                        # total_distance_km, total_duration_min,
                                        # total_cost_rub, geometry[{lat, lon}],
                                        # stops[] (см. ниже)
  metrics: Metrics
  warnings: SolverWarning[]

RouteStopResponse:
  order_id?, truck_id, warehouse_id, client_id, product_id, sequence_order,
  shipped_kg, distance_km, eta_minutes, expected_freshness, trip_leg_cost_rub,
  stop_status: "planned" | "delivered"

Metrics:
  total_tco_rub, total_trip_cost_rub, total_spoilage_loss_rub,
  expected_net_profit_rub, avg_freshness_pct, spoilage_pct, unmet_pct,
  shipped_kg, unmet_kg, total_trips, avg_load_factor_pct, split_clients

SolverWarning:
  code, message, severity: "info" | "warning" | "error", client_id?, order_id?

OrderAssignmentResponse:
  order_id, truck_id, truck_name, warehouse_id, warehouse_name,
  shipped_kg, distance_km, duration_min, trip_cost_rub,
  spoilage_loss_rub, total_cost_rub, expected_freshness, geometry[]

FixedAssignmentResponse (в составе ERPStateResponse.fixed_assignments):
  order_id, truck_id, truck_name, warehouse_id, warehouse_name,
  client_id, product_id, shipped_kg, distance_km, duration_min,
  expected_freshness, trip_cost_rub, geometry[]
```

JSON — `snake_case` с `extra="forbid"`: неизвестное поле в теле запроса даёт 422.
Проверка актуальности DTO — тесты `backend/tests/test_contract.py` и
`backend/tests/test_solver_api.py`.

---

## 10. Операции ERP и бизнес-правила

### 10.1 Изменение цены

`PATCH /erp/orders/{id}` с `purchase_price_rub > 0`. Меняет цену заявки, влияет на
доход, потери от порчи и выбор партии в следующем расчёте.

В интерфейсе цена не редактируется: заказ приходит от покупателя уже с ценой,
поэтому в таблице заказов она показана только для чтения (эндпоинт остаётся
доступным для API и импорта).

### 10.2 Этапы поставки и списание стока

Заявка проходит три этапа: `pending` — «В плане», `in_progress` — «В работе»,
`delivered` — «Доставлено». Первые два участвуют в расчёте (плановый спрос и уже
отгруженный груз соответственно), `delivered` закрывает заявку.

`PATCH /erp/orders/{id}` с `delivery_status: delivered` или `in_progress`
фиксирует отгрузку:

1. остаток спроса $= \text{requested\_kg} - \text{delivered\_kg}$;
2. если остаток нулевой — заявка сразу получает запрошенный этап;
3. иначе по стопам **последнего прогона** для этой заявки определяется, с каких
   складов и сколько везли (`_plan_consumption`), и эти килограммы списываются с
   `warehouse_stock`, а факт фиксируется в `delivered_order_stock`;
4. если стока не хватает — `409 conflict`
   (`Warehouse stock changed since the latest plan`);
5. `delivered_kg` растёт; при полной отгрузке заявка получает запрошенный этап
   (`in_progress` остаётся «в работе» до подтверждения получения, `delivered`
   закрывается), а частично отгруженная остаётся `pending` с остаточным спросом;
6. если сохранённого плана нет, заявка считается отгруженной целиком
   (`delivered_kg = requested_kg`).

Возврат `delivery_status: pending` (в том числе из «В работе») откатывает журнал:
сток возвращается на склады, `delivered_kg = 0`.

Оба отгруженных этапа (`in_progress`, `delivered`) попадают в `frozen_order_ids`,
поэтому при следующем расчёте вывезенный товар не распределяется повторно;
частично закрытая заявка передаётся в солвер остатком спроса.

**Массовая доставка.** На вкладке «Расчёт» после успешного расчёта появляется
кнопка «Отметить доставленными»: она переводит в `delivered` все заявки плана,
которые ещё не закрыты (`pending` и `in_progress`, `store.deliverOrders`), по
одному `PATCH` на заявку — сток списывается по тому же последнему прогону.
Список заявок берётся из `solver.plannedStops`, а не из всего ERP. На первой
ошибке (обычно `409`) отметка останавливается, а уведомление сообщает, сколько
заявок успело закрыться.

### 10.3 Подбор машины и маршрута для заявки

`POST /erp/orders/{id}/assign` вызывается, когда логист переводит заявку
в «В работе». Сервис `services/order_assignment.py` перебирает активные машины,
у которых на базовом складе есть сток этой культуры, и выбирает вариант
с минимальной суммой «доставка + потери»:

* ограничения — вместимость ≥ остатка спроса, допуск `can_use_dirt` для
  грунтового подъезда, активный статус машины, остаток продукта на складе;
* плечо берётся из кэша `route_cache` (Mapbox / haversine-fallback),
  время, сохранность и потери — из `freshness_math` с учётом рефрижератора
  и утепления;
* стоимость рейса — `fixed_trip_cost_rub + distance_km · cost_per_km_rub`.

Ответ `OrderAssignmentResponse` описывает выбранную машину, склад, плечо, время,
стоимость рейса, потери, сохранность и полилинию маршрута. Результат
**фиксируется** в `fixed_assignment`: маршрут восстанавливается из
`GET /erp/state` (поле `fixed_assignments`), рисуется пунктиром на карте и
учитывается в следующих расчётах как готовый рейс (§6.5). Повторный вызов
обновляет ту же фиксацию.

Списание стока выполняет `PATCH /erp/orders/{id}` со статусом `in_progress`:
если фиксация есть, килограммы списываются с её склада, иначе — по последнему
плану. Возврат в «В плане» возвращает сток и снимает фиксацию; статус
«Доставлено» закрывает заявку и тоже убирает фиксацию.

### 10.4 Машина не в работе, сток, погода

* `PATCH /erp/trucks/{id}` со `status: broken` исключает машину из расчёта
  (warning `broken_trucks_excluded`).
* `PATCH /erp/stocks/{id}` меняет доступный вес партии.
* `POST /weather/override` меняет пресет; режим сохраняется в БД.

### 10.5 Сброс демо (`reset-demo`)

Админский эндпоинт удаляет прогоны, остановки, журнал списаний, кэш маршрутов,
пресет погоды и все справочники ERP, затем заново выполняет seed и очищает кэш
погоды в памяти. Возвращает количество восстановленных сущностей.

---

## 11. Экспорт XLSX и печать

Книгу собирают четыре модуля: `xlsx_report.py` (чтение прогона и производные
показатели), `xlsx_analysis.py` (аналитические листы), `xlsx_erp.py` (таблицы
текущего ERP) и `xlsx_exporter.py` (рендеринг). Книга строится `openpyxl` в
`BytesIO` и состоит из обычных таблиц — без диаграмм и символов валюты; деньги
подписаны как «руб.». Листы прогона читают только `simulation_run` + `route_stop`,
дополнительно цена руб./кг берётся из текущей карточки заявки (в `route_stop` она
не хранится). Листы ERP читают текущее состояние БД на момент выгрузки.

* лист **«Сводка»**: заголовок с номером расчёта, дата/погода/температура/осадки,
  число машин, маржа, таблица показателей (выручка, общие затраты, доставка,
  потери руб./кг/%, прибыль, сохранность, привезли/не привезли, рейсы, загрузка,
  покупатели в нескольких рейсах) и краткая таблица рейсов;
* лист **«Рейсы»**: по машинам — оснащение (рефрижератор/утепление/грунт),
  вместимость, отгружено, загрузка %, остановок, пробег, время, выручка,
  потери ₽/кг, стоимость, маржа, сохранность; строка «Итого», автофильтр,
  закреплённая шапка;
* лист **«Аналитика»**: построчно по каждой остановке — рейс, машина, заказ,
  покупатель с адресом, тип дороги, культура, склад, свежесть партии,
  отгружено, цена, выручка, плечо и время плеча, ETA, сохранность, потери
  (кг и ₽), стоимость плеча, маржа, этап; подсветка низкой сохранности и
  отрицательной маржи, автофильтр и строка «Итого»;
* лист **«Замечания»**: пометки, рассчитанные из прогона — недовоз (кг и %),
  остановки ниже порога `SOLVER_MIN_STOP_FRESHNESS`, рейсы с загрузкой < 50 %,
  покупатели в нескольких рейсах; при отсутствии пометок — «Замечаний нет»;
* листы **«Заказы»**, **«Машины»**, **«Склады и остатки»**: те же таблицы, что на
  сайте (заявки с этапом и адресом; автопарк с оснащением и статусом; матрица
  склад × культура с итогами) — читаются из БД на момент выгрузки;
* листы **«Рейс N <госномер>»**: склад, оснащение, вместимость, загрузка,
  пробег, время, стоимость, выручка, потери, маржа, сохранность в последней
  точке, погода, таблица остановок
  (`№ / Заказ / Покупатель / Урожай / Отгружено, кг / Расстояние, км /
  В пути, мин / Сохранность, % / Стоимость, руб. / Статус`) и строка «Итого».

Ответ — `StreamingResponse` с
`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` и
`Content-Disposition: attachment; filename="agrologistix-run-<id>.xlsx"`.

**PDF** делается браузером: `window.print()` + `shared/styles/print.scss` (@media
print). Скрываются карта, шапка и панели, остаётся печатный маршрутный лист А4 с
шапкой, таблицей остановок и строками для подписей.

---

## 12. Frontend

**Вертикальные срезы** (`frontend/src/sections/`):

| Срез | Содержимое |
| :--- | :--- |
| `landing/` | публичный лендинг с единственной кнопкой входа |
| `pin-auth/` | экран 6-точечного PIN, индикатор, auth-store (роль + PIN в `sessionStorage`) |
| `erp-dashboard/` | каркас дашборда, вкладки «Заказы», «Машины и склады» (автопарк с оснащением иконками и статусом «в строю / не в работе», склады с остатками) и «Расчёт», погодная панель, excel-таблица итогов расчёта (стоимость, траты, прибыль, сохранность), предупреждения, таблица рейсов, печатный лист, сторы `useErpStore` / `useSolverStore` / `useWeatherStore` |
| `map-routing/` | Mapbox GL canvas, маркеры складов/клиентов, полилинии маршрутов, легенда, fallback-панель |

**Роутинг:** `/` (лендинг), `/login`, `/dashboard` (`meta.requiresAuth`),
неизвестные пути редиректят на `/`; guard уводит неавторизованных на `/login`,
авторизованных не пускает на `/login`.

**HTTP-клиент** (`shared/api/httpClient.ts`): база `VITE_API_BASE_URL`, заголовок
`X-Access-Pin`, разбор ошибок `{code, detail}`. В dev-режиме разрешён mock-fallback
**только для GET-запросов** (`/erp/state`, `/weather/current`) и демо-PIN:
`PATCH` и `/solver/optimize` мокать запрещено — иначе логист видел бы выдуманные
цифры.

**Состояние.**

* `useErpStore` — источник правды для ERP: загрузка состояния, тихий опрос раз в
  1 секунду, оптимистичные `PATCH`-мутации с последующим refetch. После успешной
  мутации вызывает `solver.markPlanStale()`: план остаётся на экране, но помечается
  устаревшим до повторного расчёта.
* `useSolverStore` — статус, план, метрики, предупреждения, рейсы, сгруппированные
  стопы для карты/таблиц, `optimizePlan()`, `markPlanStale()`, `clear()`.
* `useAssignmentStore` — зафиксированные маршруты заявок «В работе»: вызов
  `POST /erp/orders/{id}/assign`, `hydrate()` из `fixed_assignments` в `GET /erp/state`
  (карта и подсказки восстанавливаются после перезагрузки), `clear()` при выходе.
* `useWeatherStore` — текущая погода и переключение пресетов.
* `useNotificationStore` — тосты об успехах и ошибках.

**Этапы поставки в интерфейсе.** В таблице заказов этап выбирается меню
«В плане → В работе → Доставлено»: перед «В работе» фронт запрашивает подбор
машины и маршрута и показывает строку «Оптимально: машина · склад · плечо ·
время · сохранность»; без подходящего варианта статус не меняется. На вкладке
«Расчёт» кнопка «В работу» переводит заказы плана в «В работе»
(один `PATCH` на заказ), после чего план помечается устаревшим.

**Карта:** центрируется на Обнинске `[36.61, 55.11]`, маркеры складов и клиентов
(цвет по `road_type` и статусу доставки), полилинии рейсов из `geometry` с цветом
по машине и пунктирный слой фиксированных рейсов заявок «В работе»
(`fixed-routes`, цвет `#0f766e`) с подписью в легенде. Карточка объекта
открывается только кликом по маркеру — наведение
ничего не показывает. В карточке адрес и список заявок: каждая заявка оформлена
кнопкой, по нажатию раскрываются её
подробности (урожай, заявлено, цена, доставлено, статус, машина, остановка,
плечо, время в пути, сохранность, отгружено, стоимость плеча). Тип дороги текстом в
карточках не дублируется: его показывают цвет маркера и легенда. Раскрытые заявки
сохраняются при фоновом обновлении ERP. Модули среза: `mapPoints.ts` — сборка
модели точек, `mapPopupContent.ts` — разметка карточки, `useMapboxMarkers.ts` —
маркеры и слои рейсов. Без токена/сети показывается
fallback-панель и геометрия-ломаная от backend.

**Таблицы.** Все `v-table` дашборда используют общий класс `excel-table`
(`shared/styles/excel-table.scss`): жёсткая сетка ячеек, закреплённая серая
шапка, зебра и подсветка строки под курсором. Компоненты задают только
минимальную ширину таблицы и собственные пометки (адрес, грунтовка и т. п.).

**Типографика.** Один системный стек `--font-main` (`shared/styles/base.scss`) для
заголовков, текста и чисел: `--font-heading`, `--font-body` и `--font-mono` —
алиасы на него. Внешние шрифты не подключаются; цифры выравниваются
`font-variant-numeric: tabular-nums`, поэтому моноширинный шрифт не нужен.

**Погода.** Меню выбора погоды — три пункта с иконкой и названием, без подсказок
и без строки «Сейчас» (температура видна прямо на кнопке).

---

## 13. Тесты

Backend (`pytest`, фикстуры — `tests/conftest.py`, фабрики — `tests/solver_factory.py`):

| Файл | Что проверяет |
| :--- | :--- |
| `test_auth.py`, `test_config.py`, `test_health.py` | PIN, роли, настройки, health |
| `test_database.py`, `test_models.py`, `test_seed.py` | схема, миграции, seed и сброс |
| `test_erp_api.py`, `test_erp_patch.py` | чтение состояния и PATCH-операции, ошибки 400/404/422 |
| `test_delivery_stock.py` | списание стока, частичные доставки, откат в pending, конфликт 409 |
| `test_weather.py`, `test_distance_matrix.py` | пресеты, кэш, haversine-fallback, кэш плеч |
| `test_freshness_math.py` | формула свежести, реф, жара, дождь, грунт, клампы |
| `test_solver_core.py`, `test_solver_input.py`, `test_solver_constraints.py`, `test_solver_fallback.py`, `test_solver_invariants.py`, `test_solver_limits.py`, `test_solver_seed.py`, `test_solver_improve.py`, `test_solver_consolidation.py` | ограничения, fallback, лимиты, вход, консолидация, инварианты и детерминизм |
| `test_solver_api.py`, `test_contract.py` | контракт `/solver/optimize`, отсутствие `parent_run_id`/`comparison`, ошибки |
| `test_export_xlsx.py` | структура книги, метрики, пустой прогон, негативные сценарии |
| `test_demo_scenarios.py` | сквозные демо-сценарии |

Frontend: `vue-tsc --noEmit`, ESLint, Prettier и production-сборка Vite. Ручные
проверки с контрольными числами и curl-командами — `docs/MANUAL-TESTS.md`.

Минимальный локальный набор:

```bash
uv run --directory backend --locked --extra dev ruff check .
uv run --directory backend --locked --extra dev ruff format --check .
uv run --directory backend --locked --extra dev pytest -q
npm run lint --prefix frontend
npm run type-check --prefix frontend
npm run build --prefix frontend
bash scripts/check_loc.sh
python scripts/generate_launch_doc.py --check
```

---

## 14. CI/CD и деплой

**GitHub Actions** (`.github/workflows/ci-deploy.yml`):

1. `backend-checks` — `uv sync --locked --extra dev`, `ruff format --check`,
   `ruff check`, `pytest -q`, `scripts/check_loc.sh`, проверка актуальности
   `docs/LAUNCH.md`.
2. `frontend-checks` — `npm ci`, Prettier check, ESLint, `vue-tsc && vite build`
   (публичный Mapbox-токен прокидывается из Repository Variable).
3. `deploy` — только для `main` и не для pull request: собирает фронт на раннере,
   синхронизирует backend и `frontend/dist` по SSH/rsync, обновляет
   `/opt/agrologistix/.env`, перезапускает `agrologistix-backend.service`,
   перезагружает Nginx и проверяет health-эндпоинты.

**Прод-схема.** Nginx раздаёт `frontend/dist` со SPA-fallback на `index.html` и
проксирует `/api/` на `127.0.0.1:8000`; FastAPI работает одним процессом Uvicorn под
`systemd` с `EnvironmentFile=/opt/agrologistix/.env`; SQLite лежит в
`/opt/agrologistix/data/app.db`. HTTPS — Let's Encrypt через
`deploy/setup-https.sh` (bootstrap-конфиг → certbot webroot → TLS-конфиг →
deploy-hook и `certbot.timer`). Полные команды и переменные — `docs/LAUNCH.md`.

---

## 15. Правила разработки

* **Лимит файла:** любой `.py`, `.ts`, `.vue` — не более **500 строк**
  (`scripts/check_loc.sh` проверяет `backend/`, `frontend/src/`, `scripts/`).
  Документация и стили не ограничены.
* **Frontend:** только Vuetify 4 + scoped SCSS; **Tailwind CSS запрещён**;
  компоненты — `<script setup lang="ts">`, тип `any` запрещён ESLint-правилом.
* **Backend:** слоистая архитектура (`core` → `models`/`schemas` → `services` →
  `api/v1`), полные аннотации типов, у каждого эндпоинта есть `response_model`,
  бизнес-логика — в сервисах, а не в роутерах.
* **Ветки и коммиты:** рабочая ветка от `main`, Conventional Commits
  (`feat(solver): …`, `fix(ui): …`, `docs: …`); изменения вливаются через PR,
  после merge ветка удаляется.
* **Обновление документации:** изменение API-контрактов, формул, таблиц БД или
  настроек запуска обязано сопровождаться правкой `docs/ARCHITECTURE.md`
  (при необходимости — `docs/launch.config.json` и `docs/LAUNCH.md`).
* **Внешние зависимости:** перед merge должны проходить ruff, pytest,
  ESLint/Prettier, `vue-tsc`, сборка, `check_loc.sh` и проверка `LAUNCH.md`.

---

## 16. Известные ограничения MVP

* Один рейс на машину за расчёт; несколько выездов одной машины не моделируются.
* Рейс грузится с одного склада (базы машины): погрузка с двух складов не
  поддерживается.
* Нет ограничений режима труда водителя (обед, пересменка), окон доставки и
  живого GPS/ГЛОНАСС-трекинга.
* Нет многопользовательского RBAC/OAuth и интеграции с 1С.
* `product.base_cost_rub` хранится как справка, но в расчёте TCO не участвует —
  экономика строится на `purchase_price_rub` заявок.
* Дробление клиента между рейсами допускается только в мягком MILP-режиме, когда
  строгая группировка приводит к большему недовозу.
* Кэш погоды — в памяти процесса (сбрасывается при рестарте); кэш расстояний —
  в SQLite и переживает рестарт.
