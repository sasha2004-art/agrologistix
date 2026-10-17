# Ручные тесты: Day 4 → Day 10

Проверка backend-функциональности вручную через `curl`. Все ожидаемые значения
получены на seed-данных из `POST /api/v1/system/reset-demo`.

> **Важно про расстояния.** Контрольные числа ниже сняты **без**
> `MAPBOX_SECRET_TOKEN` — это офлайн-оценка haversine×1.3 с прямой ломаной
> (9–17 точек на плечо). С заданным токеном Mapbox расстояния, время в пути,
> сохранность и затраты будут другими, а `RouteResponse.geometry` придёт
> дорожной линией на сотни точек; структура плана и отношения (например,
> множитель осадков **1.30**) сохраняются. Записи `route_cache` со
> `source = 'fallback'` автоматически перезапрашиваются при
> первом расчете с токеном, `reset-demo` для этого не нужен.

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

Заявки (`order_id`: клиент, продукт, кг, цена ₽/кг, вес недовоза ₽/кг).
Вес недовоза — внутренний параметр MILP, в публичных метриках он не показывается:

| id | клиент | дорога | продукт | кг | цена | вес недовоза |
|---|---|---|---|---|---|---|
| 1 | ВкусВилл | asphalt | клубника | 800 | 320 | 120 |
| 2 | ВкусВилл | asphalt | томаты | 2400 | 160 | 80 |
| 3 | Агро-Рынок | asphalt | томаты | 1200 | 150 | 70 |
| 4 | Агро-Рынок | asphalt | огурцы | 700 | 110 | 50 |
| 5 | Кооператив Боровск | **dirt** | клубника | 300 | 300 | 150 |
| 6 | Кооператив Боровск | **dirt** | огурцы | 500 | 105 | 45 |
| 7 | Пятёрочка | asphalt | томаты | 1500 | 155 | 75 |
| 8 | Пятёрочка | asphalt | клубника | 350 | 310 | 140 |
| 9 | Эко-база | **dirt** | огурцы | 600 | 115 | 55 |

Машины: `1` Volvo FH16 (20 000 кг, 75 км/ч, реф, **без грунта**),
`2` ГАЗон NEXT (6 000 кг, 62 км/ч, реф, грунт),
`3` КАМАЗ Компас (10 000 кг, 70 км/ч, **без рефа**, грунт).
Склады: `1` Хаб Обнинск (55.0968, 36.6103), `2` Склад Детчино (54.8083, 36.2333).
Суммарный спрос: **8 350 кг** — дневная поставка на точку, а не размер склада.

Партии на складах имеют разную начальную свежесть `initial_freshness`
(от 0.78 до 0.97) — как в реальной холодовой цепочке:

| Склад | Клубника | Томаты | Огурцы |
|---|---|---|---|
| Хаб Обнинск | 9 000 кг / 0.97 | 22 000 кг / 0.93 | 14 000 кг / 0.90 |
| Склад Детчино | 5 000 кг / 0.82 | 12 000 кг / 0.95 | 7 000 кг / 0.78 |

Свежесть в точке доставки = `initial_freshness · exp(-λ_p · t_факт · k_temp)`,
поэтому солвер сравнивает не только расстояние, но и остаточный срок годности
партии: дешёвый рейс с подпорченной партией может проиграть более дорогому.

---

## Day 4 — ERP PATCH

### 4.1 Изменение цены заявки

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' \
  -d '{"purchase_price_rub":999}' $B/erp/orders/1
```

Ожидается `200`:

```json
{"id":1,"client_id":1,"product_id":1,"requested_kg":800.0,"purchase_price_rub":999.0,"unmet_penalty_rub":120.0,"delivered_kg":0.0,"delivery_status":"pending"}
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

Ожидается `200` и `"delivery_status":"delivered"` (с `delivered_kg: 800.0`), затем `"pending"` с `delivered_kg: 0.0`.
В интерфейсе эти статусы подписаны как «Доставлено» и **«В плане»** (раньше — «В работе»).

### 4.2.1 Фиксация доставки со списанием склада

После расчёта baseline доставка заявки списывает фактически отгруженные кг с тех
складов, откуда их повёз план:

```bash
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize)
STOCK_BEFORE=$(curl -s -H "$U" $B/erp/state | python3 -c "import sys,json;print(sum(s['available_kg'] for s in json.load(sys.stdin)['stocks']))")
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"delivered"}' $B/erp/orders/1
STOCK_AFTER=$(curl -s -H "$U" $B/erp/state | python3 -c "import sys,json;print(sum(s['available_kg'] for s in json.load(sys.stdin)['stocks']))")
python3 -c "print('списано:', $STOCK_BEFORE - $STOCK_AFTER)"
```

Ожидается, что списанный объём равен сумме `shipped_kg` остановок заявки 1 в
baseline, а `delivered_kg` в ответе — тому же числу. Повторный расчёт не должен
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

## Day 6–7 — интерфейс расчёта (frontend)

Проверяется на живом UI (`http://localhost:5173/dashboard`, PIN `202601`) при
запущенном backend. Перед сценарием: `curl -s -X POST -H "$A" $B/system/reset-demo`.

### F1. Кнопка расчёта и состояния

1. Вкладка «Расчёт» → «Маршруты ещё не рассчитаны», кнопка активна.
2. Нажмите «Рассчитать поставки» — кнопка уходит в `loading`, повторный клик
   игнорируется, полоса прогресса видна.
3. После ответа (~1 с) появляются таблица маршрутов и замечания. Кнопка меняется на «Пересчитать».
4. «Очистить» возвращает пустое состояние.

### F2. Состав вкладки «Расчёт»

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["metrics"])'
```

Плиток-метрик (затраты, прибыль, сохранность) на вкладке нет. После расчёта
появляются предупреждения и таблица маршрутов, а числовые показатели `metrics`
видны в маршрутном листе XLSX — включая понятные проценты `Потери урожая, %`
и `Не привезли, %` — и совпадают с ответом API. Печатный лист содержит
остановки рейсов и их итоги без сводки метрик.

### F3. Полилинии и легенда рейсов

На карте — по одной линии на машину, цвет линии совпадает с цветом в таблице
плана и в легенде под картой. Наведите курсор на маркер клиента: ничего не
открывается. Нажмите на маркер — откроется карточка с адресом и списком заявок;
нажмите на кнопку заказа — раскроются его подробности (урожай, кг, цена,
доставлено, статус, машина, номер остановки, плечо, время в пути, сохранность,
стоимость плеча); повторное нажатие сворачивает их.
Тип дороги в карточке текстом не выводится — только цветом маркера и легендой.
Раскрытая заявка остаётся открытой при фоновом обновлении
ERP (раз в секунду).

### F4. Замечания расчёта

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
```

Пересчитайте план в UI → в блоке «Замечания к расчёту» появляются
«Сломанные машины не участвуют в расчёте: 1» и «Жара +35 °C: часть машин едет
без охлаждения…», счётчик «Замечаний: 2», сохранность в таблице маршрутов падает.
Верните стенд: машина `active`, погода `normal`.

### F5. Низкая сохранность

На seed-данных после расчёта: строки таблицы маршрутов с сохранностью `< 0,9`
подсвечены (warning), `< 0,8` — красным (error); блок «Точки с низкой
сохранностью» перечисляет их с покупателем, машиной, временем в пути и
процентом сохранности. В блоке рисков есть партии «Склад Детчино» 82 % и 78 %.

### F6. Ошибка расчёта без mock-fallback

1. Остановите backend (`kill $(pgrep -f 'uvicorn app.main:app')`).
2. Нажмите «Пересчитать» → появляется «Не получилось рассчитать план.
   Повторите попытку.» и кнопка «Повторить расчёт»; предыдущий план и метрики
   остаются на экране (выдуманных данных нет).
3. Поднимите backend и нажмите «Повторить расчёт» → план пересчитывается.

### F7. Статус заказов и массовая доставка

1. Вкладка «Заказы»: у каждой заявки в колонке статуса — «В плане».
2. Вкладка «Расчёт» → «Рассчитать поставки»: после расчёта рядом с экспортом
   появляется кнопка «Отметить доставленными» (подсказка: «Отметить доставленными
   заказов: N»).
3. Нажмите кнопку: появляется одно уведомление «Отмечено доставленными: N из N»,
   кнопка становится неактивной («Все заказы плана уже отмечены доставленными»),
   а плашка над планом сообщает, что данные изменились и нужен пересчёт.
4. Вернитесь на «Заказы»: заявки плана теперь «Доставлено», остатки складов
   уменьшились на отгруженный объём, а заявки, не попавшие в план, остались
   «В плане».
5. Повторный расчёт не распределяет уже вывезенный товар.

---

## Day 6–7 — математика свежести и жёсткие ограничения

Все сценарии ниже — через `POST /solver/optimize` на фиксированном пресете
`heavy_rain` (16 °C, 12 мм) или `heatwave_35c`. Перед каждым: `reset-demo` +
нужный пресет.

### S1. Полный автопарк, ливень

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидаемые метрики:

```json
{"total_tco_rub":191923.87,"total_trip_cost_rub":22767.92,"total_spoilage_loss_rub":169155.95,
 "expected_net_profit_rub":1257576.13,"avg_freshness_pct":88.40,"spoilage_pct":11.60,
 "shipped_kg":8350.0,"unmet_kg":0.0,"unmet_pct":0.0}
```

Маршруты: 2 — еврофура (`truck_id=1`, 4 стопа, 5 050 кг) и ГАЗон
(`truck_id=2`, 5 стопов, 3 300 кг). КАМАЗ не понадобился: все заявки влезают
в два рейса. `warnings`: пусто. Все 8 350 кг доставлены.

Геометрия рейсов: с `MAPBOX_SECRET_TOKEN` приходит дорожная линия на сотни
точек, без токена — прямая ломаная (в этом сценарии 17 и 25 точек).
Проверить источник кэша можно так:

```bash
sqlite3 /opt/agrologistix/data/app.db \
  "select source, count(*) from route_cache group by source;"
```

Ожидается `mapbox|<число плеч>`; строки `fallback` появляются только когда API недоступен.

Проверки математики в этом ответе:

* ETA и свежесть **растут по времени** по порядку стопов внутри маршрута;
* первый стоп каждого рейса включает `fixed_trip_cost_rub` — сумма
  `trip_leg_cost_rub` по рейсу равна `total_cost_rub` (погрешность ≤ 0.05 ₽);
* `total_tco_rub = total_trip_cost_rub + total_spoilage_loss_rub` (штрафов нет);
* `spoilage_pct = 100 − avg_freshness_pct`, `unmet_pct = unmet_kg / 8 350 · 100`;
* `shipped_kg + unmet_kg = 8 350`.

### S2. Ограничение вместимости (доступен только ГАЗон, 6 000 кг)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается:

* `shipped_kg = 5750.0`, `unmet_kg = 2600.0`;
* единственный маршрут `truck_id=2`, 5 стопов, 5 750 кг (≤ `capacity_kg`);
  хвост рейса снят лимитом остановок;
* `unmet_pct = 31.14` (2 600 из 8 350 кг);
* `total_tco_rub = 119610.70` (доставка + потери, без штрафов),
  `total_trip_cost_rub = 7960.80`, `total_spoilage_loss_rub = 111649.90`,
  `avg_freshness_pct = 88.32`, `avg_load_factor_pct = 95.83`;
* `warnings`: `broken_trucks_excluded`, `unmet_demand`, `trip_limit_exceeded`.

### S3. Грунтовка недоступна (осталась только еврофура без допуска)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается:

* `shipped_kg = 6250.0`, `unmet_kg = 2100.0` (грунтовые заявки 5, 6, 9 и хвост лимита);
* `total_tco_rub = 150488.84` (доставка + потери, без штрафов),
  `total_trip_cost_rub = 15206.66`, `total_spoilage_loss_rub = 135282.18`,
  `avg_freshness_pct = 88.77`, `unmet_pct = 25.15` (2 100 из 8 350 кг);
* `routes`: только `truck_id=1` (5 стопов); **еврофура не назначена ни на одну dirt-точку**;
* `warnings`: `broken_trucks_excluded`, `unmet_demand`, `trip_limit_exceeded` и **три** `dirt_unreachable`
  с парами `client_id/order_id`: `(3,5)`, `(3,6)`, `(5,9)`.

### S4. Always-feasible: все машины сломаны

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
for t in 1 2 3; do curl -s -o /dev/null -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/$t; done
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается (без ошибок сервера):

* `routes: []`, `shipped_kg = 0.0`, `unmet_kg = 8350.0`, `avg_freshness_pct = 0.0`;
* `total_tco_rub = 0.0` (рейсов нет — нет доставки и потерь),
  `spoilage_pct = 0.0`, `unmet_pct = 100.0`;
* `warnings`: `broken_trucks_excluded`, `no_active_trucks`, `unmet_demand`,
  `dirt_unreachable` **ровно 3** (только грунтовые заявки 5, 6, 9 —
  предупреждение о грунтовке не должно появляться на асфальтовых точках).

### S5. Жара, полный автопарк — предпочтение рефрижераторов

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается: `shipped_kg = 8350.0`, `unmet_kg = 0.0`, `avg_freshness_pct = 89.44`,
`spoilage_pct = 10.56`, `total_spoilage_loss_rub = 151431.97`,
`total_tco_rub = 174199.89`, маршруты — только рефрижераторы:
`truck_id=1` (4 стопа, 5 050 кг) и `truck_id=2` (5 стопов, 3 300 кг).
`warnings`: пусто.
Мобиль без рефа (КАМАЗ) в жару не используется — порча дороже экономии.

### S6. Жара + все рефрижераторы сломаны (сценарий PRD)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается:

* `shipped_kg = 6600.0`, `unmet_kg = 1750.0`, `avg_freshness_pct = 77.29`;
* `spoilage_pct = 22.71`, `total_spoilage_loss_rub = 295827.20`,
  `total_tco_rub = 307071.12` (доставка + потери, без штрафов),
  `unmet_pct = 20.96` (1 750 из 8 350 кг);
* один маршрут на КАМАЗе (`truck_id=3`), 5 стопов;
* `warnings`: `broken_trucks_excluded`, `unmet_demand`, `heat_without_reefer`,
  `freshness_risk`, `trip_limit_exceeded`.

Сравните с S5: порча выросла почти вдвое (151 432 → 295 827), свежесть
упала с 89.44 % до 77.29 % — так система «выбирает математически
наименьший убыток».

### S7. Множитель осадков (проверка t_actual)

Сценарий S3 (осталась только еврофура) выполните дважды — под ливнем и при
нулевых осадках (`heatwave_35c`) — и сравните ETA одних и тех же стопов:

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize \
 | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['metrics'],[(s['order_id'],round(s['eta_minutes'],2),round(s['expected_freshness'],4)) for r in d['routes'] for s in r['stops']])"
```

Ожидаемые ETA одного и того же маршрута (только еврофура, 5 стопов):

| заявка | точка | `heavy_rain` (12 мм) | `heatwave_35c` (0 мм) | отношение |
|---|---|---|---|---|
| 7 | Пятёрочка, asphalt | 13.17 | 10.13 | **1.30** |
| 3 | Агро-Рынок, asphalt | 42.77 | 32.90 | **1.30** |
| 1 | ВкусВилл, asphalt | 120.26 | 92.51 | **1.30** |

Отношение точно соответствует формуле `k_rain = 1 + 0.3 · min(1; мм / 10) = 1.3`
при 12 мм. В жару тот же маршрут остаётся выгодным для рефрижератора:
`shipped_kg = 6250.0`, `unmet_kg = 2100.0`, `total_tco_rub = 135338.38`
(доставка + потери, без штрафов), `unmet_pct = 25.15`,
`avg_freshness_pct = 89.88` против 88.77 под ливнем (без замедления груз
портится меньше); порча 135 282,18 ₽ в ливень против 120 131,72 ₽ в жару.

Множитель грунтовки `k_surface = 1.35` проверяется unit-тестами
(`backend/tests/test_freshness_math.py`) и косвенно в S1: первое плечо ГАЗона
до Кооператива Боровск (грунтовка, 19.06 км) занимает 32.37 мин — это
`62 км/ч ÷ 1.35 × 1.3`; асфальтовое плечо еврофуры до Пятёрочки (12.66 км)
занимает 13.17 мин — `75 км/ч ÷ 1.3`.

---

## Day 8 — базовый расчёт и метрики

### 8.1 Ответ и структура

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize | python3 -m json.tool | head -40
```

Ожидается `200` с полями `run_id` (число ≥ 1), `routes[]` (с `geometry[]` из
`{lat, lon}` и `stops[]` с `sequence_order`, `shipped_kg`, `distance_km`,
`eta_minutes`, `expected_freshness`, `trip_leg_cost_rub`, `stop_status: "planned"`),
`metrics{}` и `warnings[]`. Полей `parent_run_id` и `comparison` в ответе нет:
план всегда строится от текущего состояния ERP, без сравнения с прошлым прогоном.

### 8.2 Согласованность метрик

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize \
 | python3 -c "import sys,json;m=json.load(sys.stdin)['metrics'];print(m['total_tco_rub'], m['total_trip_cost_rub']+m['total_spoilage_loss_rub'], m['shipped_kg']+m['unmet_kg'], m['spoilage_pct'], m['unmet_pct'])"
```

Ожидается: первые два числа равны (расхождение ≤ 0.05), третье ≈ 8 350,
четвёртое равно `100 − avg_freshness_pct`, пятое — доля недовоза от заказанного
объёма. Штрафов в публичном ответе нет: это внутренний вес недовоза в MILP.

### 8.3 Новый прогон на каждый расчёт

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])"
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])"
```

Ожидается: два разных `run_id`, второй больше первого (предыдущий не перезаписывается).

### 8.4 Производительность

```bash
curl -s -o /dev/null -w '%{time_total}s\n' -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается: на сервере (localhost) **0.07–0.15 с**; первый запрос после рестарта
с живой погодой — до 0.5 с; через Cloudflare добавляется сеть (0.5–1.7 с).
Целевой бюджет — менее 1.5 с.

### 8.5 Ошибки

Пустое тело `{}` — валидный запрос: у расчёта больше нет полей режима.
Отклоняются только неизвестные поля и запросы без PIN.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X POST -H 'Content-Type: application/json' -d '{"unexpected":1}' $B/solver/optimize  # 422
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize               # 401
```

### 8.6 Персистенция (на сервере)

```bash
sqlite3 /opt/agrologistix/data/app.db \
  "select id, weather_mode, temp_c, total_shipped_kg, total_unmet_kg from simulation_run order by id desc limit 3;
   select run_id, count(*) from route_stop group by run_id order by run_id desc limit 3;"
```

Ожидается: по одной строке `simulation_run` на расчёт (с погодным режимом и
температурой) и число `route_stop`, равное сумме стопов в ответе (для базового
плана — 9).

### 8.7 Интерфейс расчёта (frontend)

Проверяется в браузере на `http://localhost:5173`. Перед сценарием:
`curl -s -X POST -H "$A" $B/system/reset-demo`.

**UI-1. Полный сценарий login → ERP → calculate**

1. Откройте `http://localhost:5173`, введите PIN `202601` в поле ввода.
2. После входа видна карта с 7 маркерами и вкладки «Заказы», «Машины», «Расчёт».
3. Вкладка «Расчёт» → «Рассчитать поставки».

Ожидается: предупреждения и таблица маршрутов появляются меньше чем за 1,5 с
(на дев-машине ~0,2 с): 2 машины (Volvo — 4 остановки, ГАЗон — 5), всего
9 остановок; на карте — две полилинии разных цветов. Плиток-метрик на вкладке
нет — затраты и сохранность смотрите в XLSX или на печати.

**UI-2. Грунтовка в плане**

В таблице маршрутов у покупателей с `road_type: dirt` (Боровск, Таруса) есть отметка
«грунтовка» с иконкой дороги; на карте такие точки окрашены в цвет грунтовки,
а в легенде под картой есть соответствующая подпись. В карточке объекта,
открываемой нажатием, тип дороги текстом не выводится.

**UI-3. Недоступная грунтовка**

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
```

Пересчитайте план в UI. Ожидается: замечания «Сломанные машины не участвуют
в расчёте: 2», «Не удалось привезти 2100 кг…» и три «К этой точке не проехать:
нужна машина, которая может ехать по грунтовке» с чипами «Заказ №5/6/9»;
в блоке «На что обратить внимание» — «Ни одной машины, которая может ехать
по грунтовке…»; в маршрутном листе затраты на доставку ниже, чем при
полном автопарке, не привезли `2 100 кг`.
Уровень замечания виден по цветной полосе слева
(error / warning / info).
Верните машины в `active` и пересчитайте план.

**UI-4. Повторный расчёт**

Кнопка «Пересчитать» во время расчёта становится `loading` и блокируется —
второй клик не порождает новый запрос (проверьте по счётчику строк в
`simulation_run`). «Очистить» возвращает состояние «Маршруты ещё не рассчитаны».

**UI-5. Реакция на недоступный backend**

Остановите backend и нажмите «Пересчитать» — появляется «Не получилось
рассчитать план. Повторите попытку.» и кнопка «Повторить расчёт», предыдущий план не
подменяется выдуманными данными.

**UI-6. Изменение ERP помечает план устаревшим**

1. Посчитайте план на вкладке «Маршруты и TCO».
2. На вкладке «Склады и заявки» измените цену любой заявки или отметьте её
   доставленной; на «Автопарке» переведите машину в `broken`.
3. Вернитесь на «Маршруты и TCO»: план остался на экране, но появился блок
   «Исходные данные изменились — пересчитайте план поставок». Автоматического
   пересчёта нет — запустите его кнопкой «Пересчитать план»; блок исчезает.

```bash
sqlite3 backend/data/app.db "select id, weather_mode from simulation_run order by id;"
```

Ожидается: новый прогон появляется только после нажатия кнопки, а не после PATCH.

---

## Day 10 — XLSX-экспорт маршрутного листа

Экспорт работает для любого сохранённого прогона: данные берутся только из
`simulation_run` + `route_stop`, поэтому файл не зависит от текущего состояния
ERP.

### 10.1 Скачивание XLSX базового расчёта

```bash
BASE=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize)
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
каждую машину; в сводке — затраты, прибыль и сохранность урожая; в листе рейса —
шапка (машина, склад, вместимость, пробег, стоимость) и таблица остановок
`№ / Заказ / Покупатель / Урожай / Отгружено, кг / Расстояние, км / В пути, мин /
Сохранность, % / Стоимость, ₽ / Статус`, затем строка `Итого`.

Сумма `shipped_kg` по листам рейсов совпадает с `metrics.shipped_kg` расчёта.

### 10.3 XLSX после изменения ERP

Доставьте заявку и посчитайте план заново: сервер построит его по актуальным
остаткам, а экспорт возьмёт именно этот прогон.

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"delivery_status":"delivered"}' $B/erp/orders/1
NEW=$(curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize)
NID=$(echo "$NEW" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
curl -s -H "$U" -o /tmp/route-sheet-replan.xlsx $B/export/run/$NID/xlsx
uv run --directory backend python - <<'PY'
from openpyxl import load_workbook
book = load_workbook('/tmp/route-sheet-replan.xlsx')
summary = book['Сводка']
header = next(row for row in summary.iter_rows() if row[0].value == 'Показатель')
print(book.sheetnames, [cell.value for cell in header])
PY
```

Ожидается `['Сводка', 'Рейс 1 ...', ...]` и строка заголовков
`['Показатель', 'Значение']` — колонок сравнения «Было / Стало» в сводке нет;
заявка `1` не появляется в листах рейсов нового расчёта.

### 10.4 Негативные сценарии

```bash
curl -s -o /dev/null -w 'no pin:  %{http_code}\n' $B/export/run/1/xlsx
curl -s -w '\nunknown: %{http_code}\n' -H "$U" $B/export/run/9999/xlsx
```

Ожидается `401` (`code: unauthorized`) без PIN и `404`
(`code: not_found`, `detail: Расчёт №9999 не найден`) для
несуществующего расчёта. Если все машины сломаны, экспорт всё равно отдаёт
рабочий файл только с листом `Сводка`, где `Не привезли, кг` > 0.

### 10.6 Интерфейс экспорта и печати (frontend)

Проверяется в браузере. Перед сценарием: `reset-demo`.

**UI-1. Кнопки экспорта**

До расчёта плана блока экспорта нет. После расчёта на вкладке
«Расчёт» появляются «Скачать таблицу (Excel)» и «Печать / PDF», а также чип
«В лист: 2 машин, 9 остановок» — при наведении он показывает, какие именно
машины попадут в лист.

**UI-2. Скачивание XLSX**

Нажмите «Скачать таблицу (Excel)» — кнопка уходит в `loading`, браузер сохраняет файл
`agrologistix-run-{id}.xlsx` (имя берётся из `Content-Disposition`), затем
всплывает уведомление «Маршрутный лист сохранён: …».

```bash
cd ~/Downloads && python3 -c "
from openpyxl import load_workbook
wb = load_workbook('agrologistix-run-1.xlsx')
print(wb.sheetnames)
print([r[0:2] for r in wb['Сводка'].iter_rows(min_row=3, max_row=6, values_only=True)])"
```

Ожидается 3 листа: `Сводка`, `Рейс 1 <госномер>`, `Рейс 2 …`.
В сводке — `Машин = 2` и метрики сохранённого расчёта.

**UI-3. Экспорт после повторного расчёта**

После PATCH и кнопки «Пересчитать» скачайте таблицу ещё раз — в новом файле
те же листы рейсов, но без доставленного заказа: экспорт всегда берёт последний
сохранённый расчёт.

**UI-4. Печать / PDF**

Нажмите «Печать / PDF» — в предпросмотре браузера остаётся только маршрутный
лист: карта, шапка, панель управления и тосты скрыты. В листе: заголовок
с номером расчёта, датой и погодой, по блоку на каждую машину (№, покупатель и адрес,
дорога «Асфальт/Грунтовка», урожай, вес, время в пути, сохранность, стоимость),
итоги по рейсу, строки для подписей водителя/диспетчера и даты.
Формат страницы — A4 книжная, поля 12 мм, таблица заголовков повторяется
при переносе рейса на следующую страницу.

Ожидаемые числа для базового плана: 2 блока машин, 9 строк остановок,
итоги 5 050 кг / 3 300 кг, суммарно 8 350 кг.

---

## Приложение: полный сброс после тестов

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" $B/weather/current      # mode: normal
curl -s -H "$U" $B/erp/state | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:len(v) for k,v in d.items()})"
```

Ожидается: `{'warehouses': 2, 'products': 3, 'stocks': 6, 'clients': 5, 'orders': 9, 'trucks': 3}`,
все заявки `pending` (`delivered_kg = 0`), машины `active`. История прогонов
(`simulation_run`, `route_stop`), журнал списаний (`delivered_order_stock`) и
кэш маршрутов также очищаются, а остатки складов возвращаются к seed-значениям.
