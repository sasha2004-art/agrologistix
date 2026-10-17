# Ручные тесты: Day 4 → Day 10

Проверка backend-функциональности вручную через `curl`. Все ожидаемые значения
получены на seed-данных из `POST /api/v1/system/reset-demo`.

## 0. Подготовка

### Запуск локально

```bash
uv run --directory backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

### Переменные для команд

```bash
export B=http://127.0.0.1:8000/api/v1
export U='X-Access-Pin: 202601'      # dispatcher
export A='X-Access-Pin: 999999'      # admin
```

Для проверки production замените `B` на `https://prod.surf/api/v1`.

### Фиксация исходного состояния (делать перед каждым сценарием)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
```

Ожидаемый ответ:

```json
{"status":"ok","warehouses":2,"products":3,"stocks":6,"clients":5,"orders":9,"trucks":3,"seeded":true}
```

> **Важно.** Режим `normal` берёт живую погоду из Open-Meteo, поэтому абсолютные
> значения свежести и TCO в нём плавают. Для воспроизводимых проверок ниже
> используется фиксированный пресет:
>
> ```bash
> curl -s -H "$U" -X POST -H 'Content-Type: application/json' \
>   -d '{"mode":"heavy_rain"}' $B/weather/override
> ```

### Справочник seed-данных

Заявки (`order_id`: клиент, продукт, кг, цена ₽/кг, штраф ₽/кг):

| id | клиент | дорога | продукт | кг | цена | штраф |
|---|---|---|---|---|---|---|
| 1 | ВкусВилл Калуга | asphalt | клубника | 1500 | 320 | 120 |
| 2 | ВкусВилл Калуга | asphalt | томаты | 2000 | 160 | 80 |
| 3 | Агро-Рынок Малоярославец | asphalt | томаты | 1200 | 150 | 70 |
| 4 | Агро-Рынок Малоярославец | asphalt | огурцы | 900 | 110 | 50 |
| 5 | Фермерский кооператив Боровск | **dirt** | клубника | 800 | 300 | 150 |
| 6 | Фермерский кооператив Боровск | **dirt** | огурцы | 1100 | 105 | 45 |
| 7 | Пятёрочка Балабаново | asphalt | томаты | 1800 | 155 | 75 |
| 8 | Пятёрочка Балабаново | asphalt | клубника | 700 | 310 | 140 |
| 9 | Эко-база Таруса | **dirt** | огурцы | 1000 | 115 | 55 |

Машины: `1` Volvo FH16 Еврофура Реф (20 000 кг, 75 км/ч, реф, **без грунта**),
`2` ГАЗон NEXT Реф-Вездеход (6 000 кг, 62 км/ч, реф, грунт),
`3` КАМАЗ Компас Тент (10 000 кг, 70 км/ч, **без рефа**, грунт).
Склады: `1` Обнинск-Северный (55.0968, 36.6103), `2` Детчино-Агро (54.8083, 36.2333).
Суммарный спрос: **11 000 кг**.

---

## Day 4 — ERP PATCH

### 4.1 Изменение цены заявки

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' \
  -d '{"purchase_price_rub":999}' $B/erp/orders/1
```

Ожидается `200`:

```json
{"id":1,"client_id":1,"product_id":1,"requested_kg":1500.0,"purchase_price_rub":999.0,"unmet_penalty_rub":120.0,"delivered_kg":0.0,"delivery_status":"pending"}
```

Повторная загрузка состояния подтверждает сохранение:

```bash
curl -s -H "$U" $B/erp/state | python3 -c "import sys,json;print([o for o in json.load(sys.stdin)['orders'] if o['id']==1])"
```

Ожидается та же заявка с ценой `999.0`.

### 4.2 Статус доставки и возврат в pending

На этом шаге плана ещё нет, поэтому заявка просто закрывается как доставленная
(`delivered_kg` станет равным `requested_kg`).

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"delivered"}' $B/erp/orders/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"pending"}' $B/erp/orders/1
```

Ожидается `200` и `"delivery_status":"delivered"` (с `delivered_kg: 1500.0`), затем `"pending"` с `delivered_kg: 0.0`.

### 4.2.1 Фиксация доставки со списанием склада

После расчёта baseline доставка заявки списывает фактически отгруженные кг с тех
складов, откуда их повёз план:

```bash
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize)
STOCK_BEFORE=$(curl -s -H "$U" $B/erp/state | python3 -c "import sys,json;print(sum(s['available_kg'] for s in json.load(sys.stdin)['stocks']))")
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"delivered"}' $B/erp/orders/1
STOCK_AFTER=$(curl -s -H "$U" $B/erp/state | python3 -c "import sys,json;print(sum(s['available_kg'] for s in json.load(sys.stdin)['stocks']))")
python3 -c "print('списано:', $STOCK_BEFORE - $STOCK_AFTER)"
```

Ожидается, что списанный объём равен сумме `shipped_kg` остановок заявки 1 в
baseline, а `delivered_kg` в ответе — тому же числу. Повторный `what_if` не должен
распределять уже вывезенный товар: склада на него больше нет, а остаток спроса
заявки (`requested_kg - delivered_kg`) остаётся в плане.

Возврат заявки в `pending` восстанавливает остатки и очищает журнал списания.
Если остаток склада изменился после расчёта, PATCH отвечает `409` с кодом
`conflict` и подсказкой `Warehouse stock changed since the latest plan`.

### 4.3 Пустой патч заявки

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{}' $B/erp/orders/1
```

Ожидается `400`:

```json
{"code":"bad_request","detail":"Request body must contain at least one field to update"}
```

### 4.4 Несуществующий id

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"purchase_price_rub":100}' $B/erp/orders/9999
```

Ожидается `404`:

```json
{"code":"not_found","detail":"Client order with id 9999 was not found"}
```

### 4.5 Валидация значений

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"purchase_price_rub":-5}' $B/erp/orders/1
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"unexpected_field":1}' $B/erp/orders/1
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"available_kg":-1}' $B/erp/stocks/1
```

Ожидается три `422`; в теле присутствует `"code":"validation_error"` и `fields`
с именем проблемного поля.

### 4.6 Машины

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"active"}' $B/erp/trucks/1
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"flying"}' $B/erp/trucks/1
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/9999
```

Ожидается: `200` `"status":"broken"`, `200` `"status":"active"`, затем `422` и `404`.

### 4.7 Остатки склада

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"available_kg":123}' $B/erp/stocks/1
```

Ожидается `200` с `"available_kg":123.0` (`stock_id=1` — клубника на складе Обнинск).

### 4.8 Авторизация

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X PATCH -H 'Content-Type: application/json' -d '{"purchase_price_rub":100}' $B/erp/orders/1
curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Access-Pin: 000000' -X PATCH -H 'Content-Type: application/json' -d '{"purchase_price_rub":100}' $B/erp/orders/1
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X POST $B/system/reset-demo
```

Ожидается: `401`, `401`, `403` (сброс демо только админом).

---

## Day 5 — погода

### 5.1 Текущая погода

```bash
curl -s -H "$U" $B/weather/current
```

Ожидается `200`, например:

```json
{"latitude":55.11,"longitude":36.61,"temperature_c":9.1,"precipitation_mm":0.0,"weather_code":1,"mode":"normal","fetched_at":"..."}
```

`temperature_c` — живое значение Open-Meteo; если сети нет, вернётся fallback
`20.0`, `0.0`, `weather_code = 1`, и запрос всё равно завершится `200`.

### 5.2 Пресеты

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"normal"}' $B/weather/override
```

Ожидаемые значения:

| mode | temperature_c | precipitation_mm | weather_code |
|---|---|---|---|
| `heatwave_35c` | 35.0 | 0.0 | 0 |
| `heavy_rain` | 16.0 | 12.0 | 65 |
| `normal` | живая/20.0 | 0.0 | 1 или из API |

### 5.3 Ошибки и авторизация

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"snowstorm"}' $B/weather/override   # 422
curl -s -o /dev/null -w '%{http_code}\n' $B/weather/current                                                                                  # 401
```

### 5.4 Персистентность пресета и кэш

1. Установите `heatwave_35c`, перезапустите backend (`Ctrl+C` и снова `uvicorn`),
   повторите `GET /weather/current` → снова `"mode":"heatwave_35c"`, `35.0` (данные в SQLite).
2. Кэш: переключите `normal`, дважды выполните `GET /weather/current` подряд —
   `fetched_at` совпадает (второй ответ из 15-минутного кэша), время ответа меньше.
3. `POST /system/reset-demo` сбрасывает пресет → `GET /weather/current` снова `"mode":"normal"`.

---

## Day 6–7 — математика свежести и жёсткие ограничения

Все сценарии ниже — через `POST /solver/optimize` на фиксированном пресете
`heavy_rain` (16 °C, 12 мм) или `heatwave_35c`. Перед каждым: `reset-demo` +
нужный пресет.

### S1. Полный автопарк, ливень

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize
```

Ожидаемые метрики:

```json
{"total_tco_rub":228663.43,"total_trip_cost_rub":17816.35,"total_spoilage_loss_rub":210847.08,
 "total_unmet_penalty_rub":0.0,"expected_net_profit_rub":1816836.57,"avg_freshness_pct":91.98,
 "shipped_kg":11000.0,"unmet_kg":0.0}
```

Маршруты: 2 — ГАЗон (`truck_id=2`, 6 стопов, 6 000 кг) и КАМАЗ (`truck_id=3`,
4 стопа, 5 000 кг). `warnings`: пусто. Все 11 000 кг доставлены.

Проверки математики в этом ответе:

* ETA и свежесть **растут по времени** по порядку стопов внутри маршрута;
* первый стоп каждого рейса включает `fixed_trip_cost_rub` — сумма
  `trip_leg_cost_rub` по рейсу равна `total_cost_rub` (погрешность ≤ 0.05 ₽);
* `total_tco_rub = total_trip_cost_rub + total_spoilage_loss_rub + total_unmet_penalty_rub`;
* `shipped_kg + unmet_kg = 11 000`.

### S2. Ограничение вместимости (доступен только ГАЗон, 6 000 кг)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize
```

Ожидается:

* `shipped_kg = 6000.0`, `unmet_kg = 5000.0`;
* единственный маршрут `truck_id=2`, ровно 6 000 кг (≤ `capacity_kg`);
* `total_unmet_penalty_rub = 440724.9 - 7947.71 - 135277.19 = 297500.0`;
* `warnings`: `broken_trucks_excluded`, `unmet_demand`.

### S3. Грунтовка недоступна (осталась только еврофура без допуска)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize
```

Ожидается:

* `shipped_kg = 8100.0`, `unmet_kg = 2900.0` (грунтовые заявки 5, 6, 9);
* `routes`: только `truck_id=1`; **еврофура не назначена ни на одну dirt-точку**;
* `warnings`: `broken_trucks_excluded`, `unmet_demand` и **три** `dirt_unreachable`
  с парами `client_id/order_id`: `(3,5)`, `(3,6)`, `(5,9)`.

### S4. Always-feasible: все машины сломаны

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
for t in 1 2 3; do curl -s -o /dev/null -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/$t; done
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize
```

Ожидается (без ошибок сервера):

* `routes: []`, `shipped_kg = 0.0`, `unmet_kg = 11000.0`, `avg_freshness_pct = 0.0`;
* `total_tco_rub = total_unmet_penalty_rub = 926500.0`;
* `warnings`: `broken_trucks_excluded`, `no_active_trucks`, `unmet_demand`,
  `dirt_unreachable` **ровно 3** (только грунтовые заявки 5, 6, 9 —
  предупреждение о грунтовке не должно появляться на асфальтовых точках).

### S5. Жара, полный автопарк — предпочтение рефрижераторов

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize
```

Ожидается: `shipped_kg = 11000.0`, `unmet_kg = 0.0`, `avg_freshness_pct = 96.09`,
`total_spoilage_loss_rub = 97721.72`, `total_tco_rub = 120489.64`,
маршруты — только рефрижераторы (`truck_id` 1 и 2). `warnings`: пусто.
Мобиль без рефа (КАМАЗ) в жару не используется — порча дороже экономии.

### S6. Жара + все рефрижераторы сломаны (сценарий PRD)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize
```

Ожидается:

* `shipped_kg = 10000.0`, `unmet_kg = 1000.0`, `avg_freshness_pct = 77.3`;
* `total_spoilage_loss_rub = 532303.82`, `total_tco_rub = 633520.34`;
* один маршрут на КАМАЗе (`truck_id=3`), 9 стопов;
* `warnings`: `broken_trucks_excluded`, `unmet_demand`, `heat_without_reefer`.

Сравните с S5: порча выросла в 5.4 раза, свежесть упала с 96.09 % до 77.3 % —
так система «выбирает математически наименьший убыток».

### S7. Множитель осадков (проверка t_actual)

Сценарий S2 выполните дважды — под ливнем и при нулевых осадках
(`heatwave_35c`), — сохраняя ETA стопов:

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize \
 | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['metrics'],[(s['order_id'],round(s['eta_minutes'],2),round(s['expected_freshness'],4)) for r in d['routes'] for s in r['stops']])"
```

Ожидаемые ETA одного и того же маршрута (только ГАЗон):

| заявка | точка | `heavy_rain` (12 мм) | `heatwave_35c` (0 мм) | отношение |
|---|---|---|---|---|
| 5 | Боровск, dirt | 41.34 | 31.80 | **1.30** |
| 7 | Балабаново, asphalt | 15.93 | 12.25 | **1.30** |
| 1 | Калуга, asphalt | 169.65 | 130.50 | **1.30** |

Отношение точно соответствует формуле `k_rain = 1 + 0.3 · min(1; мм / 10) = 1.3`
при 12 мм. Дополнительно в этом сценарии (`heatwave_35c`, только ГАЗон-реф):
`shipped_kg = 6000.0`, `unmet_kg = 5000.0`, `total_tco_rub = 411647.94`,
`avg_freshness_pct = 93.59` (против 91.82 под ливнем — без замедления груз
портится меньше).

Множитель грунтовки `k_surface = 1.35` проверяется unit-тестами
(`backend/tests/test_freshness_math.py`) и косвенно: ETA грунтовой точки
Боровск (41.34 мин под ливнем) заметно больше ETA асфальтового Балабаново
(15.93 мин) при сопоставимом плече (13.9 км против 10.1 км по прямой).

---

## Day 8 — базовый расчёт и метрики

### 8.1 Ответ и структура

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize | python3 -m json.tool | head -40
```

Ожидается `200` с полями `run_id` (число ≥ 1), `parent_run_id: null`,
`routes[]` (с `geometry[]` из `{lat, lon}` и `stops[]` с `sequence_order`,
`shipped_kg`, `distance_km`, `eta_minutes`, `expected_freshness`,
`trip_leg_cost_rub`, `stop_status: "planned"`), `metrics{}`, `warnings[]`,
`comparison: null`.

### 8.2 Согласованность метрик

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize \
 | python3 -c "import sys,json;m=json.load(sys.stdin)['metrics'];print(m['total_tco_rub'], m['total_trip_cost_rub']+m['total_spoilage_loss_rub']+m['total_unmet_penalty_rub'], m['shipped_kg']+m['unmet_kg'])"
```

Ожидается: первые два числа равны (расхождение ≤ 0.05), третье ≈ 11 000.

### 8.3 Новый прогон на каждый расчёт

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])"
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])"
```

Ожидается: два разных `run_id`, второй больше первого (предыдущий не перезаписывается).

### 8.4 Производительность

```bash
curl -s -o /dev/null -w '%{time_total}s\n' -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize
```

Ожидается: на сервере (localhost) **0.07–0.15 с**; первый запрос после рестарта
с живой погодой — до 0.5 с; через Cloudflare добавляется сеть (0.5–1.7 с).
Целевой бюджет — менее 1.5 с.

### 8.5 Ошибки

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize                 # 422
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline","x":1}' $B/solver/optimize  # 422
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize               # 401
```

### 8.6 Персистенция (на сервере)

```bash
sqlite3 /opt/agrologistix/data/app.db \
  "select id, parent_run_id, weather_mode, temp_c, total_shipped_kg, total_unmet_kg from simulation_run order by id desc limit 3;
   select run_id, count(*) from route_stop group by run_id order by run_id desc limit 3;"
```

Ожидается: по одной строке `simulation_run` на расчёт (с погодным режимом и
температурой) и число `route_stop`, равное сумме стопов в ответе (для базового
плана — 10).

---

## Day 9 — «Что, если» и сравнение «Было / Стало»

### 9.1 Сначала сохраните базовый расчёт

```bash
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize)
RID=$(echo "$BASE" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
echo "baseline run_id=$RID"
```

### 9.2 Ошибки режима what_if

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"what_if"}' $B/solver/optimize        # 422 (нужен baseline_run_id)
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"what_if","baseline_run_id":9999}' $B/solver/optimize                   # 404
```

Ожидается `422` (`fields.baseline_run_id`) и `404`:

```json
{"code":"not_found","detail":"Simulation run with id 9999 was not found"}
```

### 9.3 Без изменений — нулевая дельта

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d "{\"mode\":\"what_if\",\"baseline_run_id\":$RID}" $B/solver/optimize \
 | python3 -c "import sys,json;c=json.load(sys.stdin)['comparison'];print(c['total_tco_rub'], c['shipped_kg'])"
```

Ожидается: `delta = 0.0` по всем метрикам с ненулевой базой;
для `unmet_kg`/`unmet_penalty` при базе `0` → `delta_pct: null`.

### 9.4 Полный сценарий PRD: delivered → broken → price → what_if

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize)
RID=$(echo "$BASE" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")

curl -s -o /dev/null -w 'delivered: %{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"delivered"}' $B/erp/orders/1
curl -s -o /dev/null -w 'broken:    %{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -o /dev/null -w 'price:     %{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"purchase_price_rub":500}' $B/erp/orders/2

curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d "{\"mode\":\"what_if\",\"baseline_run_id\":$RID}" $B/solver/optimize \
 | python3 -c "import sys,json;d=json.load(sys.stdin);print(json.dumps(d['comparison'],ensure_ascii=False,indent=1))"
```

Ожидается `200` на три PATCH и сравнение:

| Метрика | Было | Стало | Δ | Δ% |
|---|---|---|---|---|
| `total_tco_rub` | 228663.43 | 161843.10 | −66 820.33 | −29.22 |
| `total_trip_cost_rub` | 17816.35 | 24132.21 | +6 315.86 | +35.45 |
| `total_spoilage_loss_rub` | 210847.08 | 137710.89 | −73 136.19 | −34.69 |
| `expected_net_profit_rub` | 1816836.57 | 2083656.90 | +266 820.33 | +14.69 |
| `avg_freshness_pct` | 91.98 | 94.15 | +2.17 | +2.36 |
| `shipped_kg` | 11000.00 | 9500.00 | −1 500.00 | −13.64 |
| `total_unmet_penalty_rub` | 0.00 | 0.00 | 0.00 | `null` |
| `unmet_kg` | 0.00 | 0.00 | 0.00 | `null` |

Дополнительно проверьте в том же ответе:

* `parent_run_id` равен `$RID`, `run_id` — новое число (больше базового);
* заявки 1 нет среди `routes[].stops[].order_id`;
* `truck_id=2` отсутствует среди маршрутов;
* `warnings` содержит `broken_trucks_excluded`.

Инвариант списания: сумма `delivered_kg` по доставленным заявкам плюс текущие
`available_kg` складов равна исходному остатку после `reset-demo` — то есть
вывезенный товар больше не может попасть в новый план.

### 9.5 Несколько заявок одного клиента

Клиент 1 (ВкусВилл) имеет заявки 1 и 2. Доставьте только первую:

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize)
RID=$(echo "$BASE" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
curl -s -o /dev/null -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"delivered"}' $B/erp/orders/1
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d "{\"mode\":\"what_if\",\"baseline_run_id\":$RID}" $B/solver/optimize \
 | python3 -c "import sys,json;s={x['order_id'] for r in json.load(sys.stdin)['routes'] for x in r['stops']};print(sorted(s))"
```

Ожидается: в списке **нет** `1`, но присутствует `2` (вторая заявка того же
клиента не отменяется). `shipped_kg = 9500` (минус 1500 кг доставленной заявки).

### 9.6 Полная потеря транспорта в what_if

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize)
RID=$(echo "$BASE" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
for t in 1 2 3; do curl -s -o /dev/null -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/$t; done
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d "{\"mode\":\"what_if\",\"baseline_run_id\":$RID}" $B/solver/optimize \
 | python3 -c "import sys,json;d=json.load(sys.stdin);c=d['comparison'];print('routes:',d['routes'],'unmet:',c['unmet_kg'])"
```

Ожидается: `routes: []`, `unmet_kg.before = 0.0`, `after = 11000.0`,
`delta_pct: null` (деление на ноль не выполняется), warnings:
`broken_trucks_excluded`, `no_active_trucks`, `unmet_demand`, `dirt_unreachable` ×3.

### 9.7 Жара + сломанные рефрижераторы в what_if

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize)
RID=$(echo "$BASE" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
curl -s -o /dev/null -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -o /dev/null -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d "{\"mode\":\"what_if\",\"baseline_run_id\":$RID}" $B/solver/optimize \
 | python3 -c "import sys,json;d=json.load(sys.stdin);c=d['comparison'];print(c['avg_freshness_pct'],c['total_spoilage_loss_rub'],c['unmet_kg'],[w['code'] for w in d['warnings']])"
```

Ожидается: `avg_freshness_pct.delta < 0`, `total_spoilage_loss_rub.delta > 0`,
`unmet_kg.after = 1000.0`, warnings включают `heat_without_reefer`.

### 9.8 Базовый план неизменяем

После выполнения 9.4/9.5 снова запросите базовый `run_id` через БД:

```bash
sqlite3 /opt/agrologistix/data/app.db "select id, parent_run_id, total_tco_rub from simulation_run;"
```

Ожидается: строка базового прогона не изменилась (`parent_run_id` = null,
метрики те же), а новый прогон ссылается на неё через `parent_run_id`.

---

## Day 10 — XLSX-экспорт маршрутного листа

Экспорт работает и для базового расчёта, и для «Что, если»: данные берутся
только из сохранённого прогона (`simulation_run` + `route_stop`), поэтому файл
не зависит от текущего состояния ERP.

### 10.1 Скачивание XLSX базового расчёта

```bash
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"baseline"}' $B/solver/optimize)
RID=$(echo "$BASE" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
curl -s -D /tmp/export-headers.txt -o /tmp/route-sheet.xlsx -H "$U" $B/export/run/$RID/xlsx
grep -i 'HTTP/\|content-type\|content-disposition\|content-length' /tmp/export-headers.txt
```

Ожидается `200` и заголовки:

```text
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="agrologistix-run-<id>.xlsx"
```

### 10.2 Проверка структуры файла

```bash
uv run --directory backend python - <<'PY'
from openpyxl import load_workbook
book = load_workbook('/tmp/route-sheet.xlsx')
print(book.sheetnames)
print([c.value for c in book['Сводка'][1]])
sheet = book[book.sheetnames[1]]
for row in sheet.iter_rows(min_row=1, max_row=6, values_only=True):
    print(row)
PY
```

Ожидается: первый лист `Сводка`, затем по одному листу `Рейс N <номер>` на
каждую машину; в сводке — метрики TCO, свежести и недовоза; в листе рейса —
шапка (машина, склад, вместимость, пробег, стоимость) и таблица остановок
`№ / Заявка / Клиент / Культура / Отгружено, кг / Участок, км / ETA, мин /
Свежесть, % / Стоимость участка, ₽ / Статус`, затем строка `Итого`.

Сумма `shipped_kg` по листам рейсов совпадает с `metrics.shipped_kg` расчёта.

### 10.3 XLSX для «Что, если»

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"delivery_status":"delivered"}' $B/erp/orders/1
WIF=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d "{\"mode\":\"what_if\",\"baseline_run_id\":$RID}" $B/solver/optimize)
WID=$(echo "$WIF" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
curl -s -H "$U" -o /tmp/route-sheet-wif.xlsx $B/export/run/$WID/xlsx
uv run --directory backend python - <<'PY'
from openpyxl import load_workbook
book = load_workbook('/tmp/route-sheet-wif.xlsx')
summary = book['Сводка']
header = next(row for row in summary.iter_rows() if row[0].value == 'Показатель')
print(book.sheetnames, [cell.value for cell in header])
PY
```

Ожидается `['Сводка', 'Рейс 1 ...', ...]` и строка заголовков
`['Показатель', 'Значение', 'Было (№<базовый>)', 'Δ']`: в сводке есть сравнение
«Было / Стало» с базовым расчётом.

### 10.4 Негативные сценарии

```bash
curl -s -o /dev/null -w 'no pin:  %{http_code}\n' $B/export/run/1/xlsx
curl -s -w '\nunknown: %{http_code}\n' -H "$U" $B/export/run/9999/xlsx
```

Ожидается `401` (`code: unauthorized`) без PIN и `404`
(`code: not_found`, `detail: Solver run with id 9999 was not found`) для
несуществующего расчёта. Если все машины сломаны, экспорт всё равно отдаёт
рабочий файл только с листом `Сводка`, где `Недовоз, кг` > 0.

---

## Приложение: полный сброс после тестов

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" $B/weather/current      # mode: normal
curl -s -H "$U" $B/erp/state | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:len(v) for k,v in d.items()})"
```

Ожидается: `{'warehouses': 2, 'products': 3, 'stocks': 6, 'clients': 5, 'orders': 9, 'trucks': 3}`,
все заявки `pending`, машины `active`. История прогонов (`simulation_run`,
`route_stop`) и кэш маршрутов также очищаются.
