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
| 1 | ВкусВилл | asphalt | клубника | 400 | 160 | 60 |
| 2 | ВкусВилл | asphalt | томаты | 1200 | 80 | 40 |
| 3 | Агро-Рынок | asphalt | томаты | 600 | 75 | 35 |
| 4 | Агро-Рынок | asphalt | огурцы | 350 | 55 | 25 |
| 5 | Кооператив Боровск | **dirt** | клубника | 150 | 150 | 75 |
| 6 | Кооператив Боровск | **dirt** | огурцы | 250 | 52.5 | 22.5 |
| 7 | Пятёрочка | asphalt | томаты | 750 | 77.5 | 37.5 |
| 8 | Пятёрочка | asphalt | клубника | 175 | 155 | 70 |
| 9 | Эко-база | **dirt** | огурцы | 300 | 57.5 | 27.5 |

Машины: `1` Volvo FH16 (10 000 кг, 75 км/ч, реф, **без грунта**),
`2` ГАЗон NEXT (3 000 кг, 62 км/ч, реф, грунт),
`3` КАМАЗ Компас (5 000 кг, 70 км/ч, **без рефа**, утеплённый кузов, грунт).
Оснащение утеплением (`has_insulation`) — это изотермический кузов без
холодильной установки: порог тепловой порчи сдвигается с +22 °C до +28 °C.
Рефрижератор держит `k_temp = 1.0` при любой жаре, поэтому в S5 выигрывает.
Склады: `1` Хаб Обнинск (55.0968, 36.6103), `2` Склад Детчино (54.8083, 36.2333).
Суммарный спрос: **4 175 кг** — дневная поставка на точку, а не размер склада.

Партии на складах имеют разную начальную свежесть `initial_freshness`
(от 0.78 до 0.97) — как в реальной холодовой цепочке:

| Склад | Клубника | Томаты | Огурцы |
|---|---|---|---|
| Хаб Обнинск | 4 500 кг / 0.97 | 11 000 кг / 0.93 | 7 000 кг / 0.90 |
| Склад Детчино | 2 500 кг / 0.82 | 6 000 кг / 0.95 | 3 500 кг / 0.78 |

Свежесть в точке доставки = `initial_freshness · exp(-λ_p · t_факт · k_temp)`,
поэтому солвер сравнивает не только расстояние, но и остаточный срок годности
партии: дешёвый рейс с подпорченной партией может проиграть более дорогому.

---

## Day 4 — ERP PATCH

### 4.1 Изменение цены заявки (только через API)

В интерфейсе цена за кг не редактируется: заказ приходит от покупателя уже
с ценой, в таблице она показана только для чтения. Сам PATCH остаётся в API
и проверяется так:

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' \
  -d '{"purchase_price_rub":999}' $B/erp/orders/1
```

Ожидается `200`:

```json
{"id":1,"client_id":1,"product_id":1,"requested_kg":400.0,"purchase_price_rub":999.0,"unmet_penalty_rub":60.0,"delivered_kg":0.0,"delivery_status":"pending"}
```

Повторная загрузка состояния подтверждает сохранение:

```bash
curl -s -H "$U" $B/erp/state | python3 -c "import sys,json;print([o for o in json.load(sys.stdin)['orders'] if o['id']==1])"
```

Ожидается та же заявка с ценой `999.0`.

### 4.2 Три этапа доставки и возврат в «В плане»

На этом шаге плана ещё нет, поэтому заявка просто считается отгруженной целиком
(`delivered_kg` станет равным `requested_kg`).

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"in_progress"}' $B/erp/orders/1
curl -s -o /dev/null -w '%{http_code}\n' -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"flying"}' $B/erp/orders/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"delivered"}' $B/erp/orders/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"delivery_status":"pending"}' $B/erp/orders/1
```

Ожидается: `in_progress` с `delivered_kg: 400.0`, затем `422` на неизвестный этап,
затем `delivered` (сток повторно не списывается) и `pending` с `delivered_kg: 0.0`.
В интерфейсе этапы подписаны «В плане», «В работе» и «Доставлено».

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

### 4.9 Защита от перебора PIN

Шестизначный PIN нельзя перебирать неограниченно: `/auth/verify-pin` считает
неудачные попытки и блокирует адрес.

```bash
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "$i: %{http_code} %{header_json}\n" \
    -X POST -H 'X-Access-Pin: 000000' $B/auth/verify-pin | head -c 120; echo
done
```

Ожидается: первые `AUTH_RATE_LIMIT_MAX_ATTEMPTS` (по умолчанию 10) ответов —
`401`, затем `429` с телом `{"code":"too_many_requests", ...}` и заголовком
`Retry-After`. Блокировка распространяется и на верный PIN — адрес уже
ограничен; после `AUTH_RATE_LIMIT_BLOCK_SEC` (300 с) попытки снова
принимаются, а успешный вход сбрасывает счётчик раньше.

В production тот же лимит включён в Nginx зоной `agrologistix_auth`
(6 запросов/мин на адрес, `deploy/nginx/agrologistix-limits.conf`), поэтому
перебор упирается в `429` ещё до приложения.

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
3. После ответа (~1 с) появляются итоги расчёта, замечания и таблица маршрутов.
   Кнопка меняется на «Пересчитать».
4. «Очистить» возвращает пустое состояние.

### F2. Состав вкладки «Расчёт»

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["metrics"])'
```

На вкладке нет плиток-метрик и штампа «Рассчитано …»: после расчёта первыми
идут «Итоги расчёта» — excel-таблица из двух колонок (показатель и значение):
итоговая стоимость, затраты на доставку, потери урожая с процентом, прибыль,
сохранность урожая и, при недовозе, строка «Не привезли» с процентом от
заказанного объёма. Ниже — предупреждения и таблица маршрутов. Те же числа
есть в маршрутном листе XLSX (включая проценты `Потери урожая, %`
и `Не привезли, %`) и совпадают с ответом API. Печатный лист содержит
остановки рейсов и их итоги без сводки метрик.

### F3. Полилинии и легенда рейсов

На карте — по одной линии на машину, цвет линии совпадает с цветом в таблице
плана и в легенде под картой. Наведите курсор на маркер клиента — выпадет
карточка с адресом и списком заявок; наведите курсор на строку заказа —
раскроются его подробности (урожай, кг, цена, доставлено, статус, машина,
номер остановки, плечо, время в пути, сохранность, стоимость плеча).
Нажатие на строку закрепляет раскрытие, нажатие на маркер закрепляет карточку
целиком (повторное нажатие закрывает её); без закрепления карточка закрывается
после ухода курсора, с клавиатуры открывается фокусом на маркере.
Тип дороги в карточке текстом не выводится — только цветом маркера и легендой.
Раскрытая заявка остаётся открытой при фоновом обновлении
ERP (раз в секунду).

### F4. Замечания расчёта

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
```

Пересчитайте план в UI → в блоке «Замечания к расчёту» появляются
«Не в работе: 1 — в расчёте не участвуют» и «Жара +35 °C: часть машин едет
без охлаждения…», счётчик «Замечаний: 2», сохранность в таблице маршрутов падает.
Верните стенд: машина `active`, погода `normal`.

### F5. Низкая сохранность

На seed-данных после расчёта: строки таблицы маршрутов с сохранностью `< 0,9`
подсвечены (warning), `< 0,8` — красным (error); блок «Точки с низкой
сохранностью» — excel-таблица из одной колонки: каждая точка отдельной строкой
с покупателем, машиной и процентом сохранности. В блоке рисков есть партии
«Склад Детчино» 82 % и 78 %.

### F6. Ошибка расчёта без mock-fallback

1. Остановите backend (`kill $(pgrep -f 'uvicorn app.main:app')`).
2. Нажмите «Пересчитать» → появляется «Не получилось рассчитать план.
   Повторите попытку.» и кнопка «Повторить расчёт»; предыдущий план и метрики
   остаются на экране (выдуманных данных нет).
3. Поднимите backend и нажмите «Повторить расчёт» → план пересчитывается.

### F7. Этапы поставки, подбор машины и массовая работа

1. Вкладка «Заказы»: в колонке статуса у каждой заявки кнопка этапа — по нажатию
   открывается меню из трёх этапов: «В плане», «В работе», «Доставлено».
2. Переведите одну заявку в «В работе»: сервис подбирает оптимальные маршрут и
   машину (минимум «доставка + потери»), показывает уведомление
   «Оптимально: <машина> · <склад> · <км> · <время> · сохранность <N> %»
   и **фиксирует маршрут**: на карте от склада к покупателю появляется
   пунктирная линия (легенда «Фиксированный рейс заявки „В работе“»), а карта
   подлетает к новому маршруту, в строке заявки — та же строка «Оптимально: …», остатки культуры
   уменьшаются именно со склада фиксации, сама заявка остаётся открытой.
3. Негативный случай: если стока нет, машины не в работе или нужен недопущенный
   на грунт транспорт, backend отвечает `409`, статус не меняется, а всплывает
   причина «Нет подходящей машины…».
   Подбор не превышает уже занятый ресурс: свободная вместимость машины,
   лимит остановок и невыбранный фиксациями сток склада проверяются до
   сохранения. Например, если сток клубники — 500 кг, а заявка 1 уже заняла
   400 кг, подбор заявки 5 (ещё 150 кг) отвечает `409`.
   Возврат заявки в «В плане» снимает фиксацию: пунктир с карты исчезает,
   сток возвращается, заявка снова участвует в расчёте.
4. Вкладка «Расчёт» → «Рассчитать поставки»: фиксированная заявка входит в план
   готовым рейсом (та же машина), а её машина не везёт другие заявки; отгруженная
   без фиксации заявка в план не попадает.
   После расчёта рядом с экспортом появляется кнопка «В работу»
   (подсказка «Взять в работу заказов: N»).
5. Нажмите кнопку: для каждого заказа плана сначала фиксируется подобранный
   маршрут (на карте появляются пунктирные линии), затем одно уведомление
   «Взято в работу: N из N», кнопка становится неактивной («Все заказы плана уже
   в работе»), а плашка над планом сообщает, что данные изменились и нужен
   пересчёт. Заявки, для которых подбор не прошёл, в работу не переводятся:
   всплывает предупреждение «Маршрут закреплён не для всех заказов: N из M»,
   такие заявки остаются «В плане».
   Отдельно: заявки «В работе» без фиксации (статус поставили до подбора или до
   этого обновления) получают маршрут автоматически при открытии вкладки
   «Заказы»: сервис подбирает и фиксирует варианты, и пунктир появляется на карте.
   Повторный выбор «В работе» в меню заявки пересобирает её фиксацию.
6. Вернитесь на «Заказы»: заявки плана теперь «В работе» (без фиксации — они
   отгружены по последнему плану), остатки складов не меняются повторно,
   а заявки, не попавшие в план, остались «В плане».
7. Повторный расчёт не распределяет уже вывезенный товар; несколько фиксаций
   одной машины собираются в один мультистоп-рейс: в таблице рейсов по строке
   на машину, суммарный груз не превышает вместимость, а число остановок —
   лимит `SOLVER_MAX_STOPS_PER_TRIP`. Склад и полилиния остаются из фиксации.
8. Поломка машины после фиксации: переведите машину фиксации в «Не в работе» и
   пересчитайте план. Рейс на ней в план не строится, в «Замечаниях» появляется
   «Машина «…» не в работе: зафиксированный рейс заказа №… в план не вошёл».
   Верните машину в строй — рейс возвращается на прежнюю машину без повторного
   подбора.

### F8. Оснащение и статус машины

Вкладка «Машины и склады». Колонка «Оснащение» содержит только иконки, без текста;
расшифровка — в подсказке при наведении и в `aria-label`:

| Иконка | Значение |
|---|---|
| `mdi-snowflake` | рефрижератор (охлаждение) |
| `mdi-weather-sunny` | без охлаждения |
| `mdi-thermometer-low` | утеплённый (изотермический) кузов — только если есть |
| `mdi-image-filter-hdr` | может ехать по грунтовке |
| `mdi-highway` | только асфальт |

У КАМАЗа видны три иконки: «без охлаждения», «утепление», «грунтовка»;
у Volvo и ГАЗона — «рефрижератор» и дорога. Кнопка статуса показывает
«В строю» или «Не в работе»; нажатие переключает состояние, и план
помечается устаревшим (пересчитайте его).

В таблице «Заказы покупателей» колонка «Дорога» тоже без текста: `mdi-image-filter-hdr`
(оранжевая) — грунтовка, `mdi-highway` (серая) — асфальт; расшифровка — в подсказке
при наведении и в `aria-label`. Это те же иконки, что в оснащении машин.

---

## Day 6–7 — математика свежести и ограничения рейса

Жёстко снимают стоп только лимит остановок и длительность смены; свежесть ниже
порога — предупреждение (`freshness_risk`), груз везётся, а потери уже в TCO.

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
{"total_tco_rub":60354.79,"total_trip_cost_rub":8219.07,"total_spoilage_loss_rub":52135.72,
 "expected_net_profit_rub":302020.21,"avg_freshness_pct":86.64,"spoilage_pct":13.36,
 "shipped_kg":4175.0,"unmet_kg":0.0,"unmet_pct":0.0}
```

Маршруты: 2 — ГАЗон (`truck_id=2`, 5 стопов, 1 625 кг, 113.28 км, 185.80 мин)
и КАМАЗ (`truck_id=3`, 4 стопа, 2 550 кг, 110.33 км, 122.94 мин). Еврофура
(`truck_id=1`) не понадобилась: утеплённый КАМАЗ в ливень выигрывает по сумме
«доставка + потери». `warnings`: один `freshness_risk` — клубника заявки 1
приезжает во ВкусВилл с сохранностью 69.6 % (порог 70 %). Все 4 175 кг доставлены.

Геометрия рейсов: с `MAPBOX_SECRET_TOKEN` приходит дорожная линия на сотни
точек (без токена — прямая ломаная из 8 сегментов на плечо).
Проверить источник кэша можно так:

```bash
sqlite3 /opt/agrologistix/data/app.db \
  "select source, count(*) from route_cache group by source;"
```

Ожидается `mapbox|<число плеч>`; строки `fallback` появляются только когда API недоступен.

Проверки математики в этом ответе:

* ETA и свежесть монотонны по порядку стопов внутри маршрута: у двух заявок
  одного покупателя плечо равно нулю, поэтому ETA совпадает (например, стопы 7
  и 8 Пятёрочки);
* первый стоп каждого рейса включает `fixed_trip_cost_rub` — сумма
  `trip_leg_cost_rub` по стопам рейса равна его `total_cost_rub`: ГАЗон
  3712.43 ₽, КАМАЗ 4506.64 ₽ (итого 8219.07 ₽, погрешность ≤ 0.05 ₽);
* `total_tco_rub = total_trip_cost_rub + total_spoilage_loss_rub` (штрафов нет);
* `spoilage_pct = 100 − avg_freshness_pct`, `unmet_pct = unmet_kg / 4 175 · 100`;
* `shipped_kg + unmet_kg = 4 175`.

### S2. Ограничение вместимости (доступен только ГАЗон, 3 000 кг)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается:

* `shipped_kg = 2875.0`, `unmet_kg = 1300.0`;
* единственный маршрут `truck_id=2`, 5 стопов, 2 875 кг; хвост рейса снят
  лимитом остановок, поэтому вместимость недоиспользована;
* `unmet_pct = 31.14` (1 300 из 4 175 кг);
* `total_tco_rub = 31892.87` (доставка + потери, без штрафов),
  `total_trip_cost_rub = 3980.40`, `total_spoilage_loss_rub = 27912.47`,
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

* `shipped_kg = 3125.0`, `unmet_kg = 1050.0` (грунтовые заявки 5, 6, 9 и хвост лимита);
* `total_tco_rub = 41423.87` (доставка + потери, без штрафов),
  `total_trip_cost_rub = 7603.33`, `total_spoilage_loss_rub = 33820.54`,
  `avg_freshness_pct = 88.77`, `unmet_pct = 25.15` (1 050 из 4 175 кг);
* `routes`: только `truck_id=1` (5 стопов, 3 125 кг, 115.63 км, 120.30 мин);
  **еврофура не назначена ни на одну dirt-точку**;
* `warnings`: `broken_trucks_excluded`, `unmet_demand`, `trip_limit_exceeded` и **три** `dirt_unreachable`
  с парами `client_id/order_id`: `(3,5)`, `(3,6)`, `(5,9)`.

### S4. Always-feasible: все машины не в работе

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heavy_rain"}' $B/weather/override
for t in 1 2 3; do curl -s -o /dev/null -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/$t; done
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается (без ошибок сервера):

* `routes: []`, `shipped_kg = 0.0`, `unmet_kg = 4175.0`, `avg_freshness_pct = 0.0`;
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

Ожидается: `shipped_kg = 4175.0`, `unmet_kg = 0.0`, `avg_freshness_pct = 86.43`,
`spoilage_pct = 13.57`, `total_spoilage_loss_rub = 52433.65`,
`total_tco_rub = 62857.80`, `total_trip_cost_rub = 10424.15`, маршруты — только
рефрижераторы: `truck_id=1` (4 стопа, 1 875 кг) и `truck_id=2` (5 стопов, 2 300 кг).
`warnings`: пусто.
Мобиль без рефа (КАМАЗ) в жару не используется — порча дороже экономии.

### S6. Жара + все рефрижераторы не в работе (сценарий PRD)

```bash
curl -s -X POST -H "$A" $B/system/reset-demo
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{"mode":"heatwave_35c"}' $B/weather/override
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/1
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X POST -H 'Content-Type: application/json' -d '{}' $B/solver/optimize
```

Ожидается:

* `shipped_kg = 3300.0`, `unmet_kg = 875.0`, `avg_freshness_pct = 82.27`;
* `spoilage_pct = 17.73`, `total_spoilage_loss_rub = 57498.43`,
  `total_tco_rub = 63120.39` (доставка + потери, без штрафов),
  `total_trip_cost_rub = 5621.96`, `unmet_pct = 20.96` (875 из 4 175 кг);
* один маршрут на КАМАЗе (`truck_id=3`), 5 стопов;
* `warnings`: `broken_trucks_excluded`, `unmet_demand`, `heat_without_reefer`,
  `freshness_risk`, `trip_limit_exceeded`.

Сравните с S5: порча выросла в 1.10 раза (52 434 → 57 498 ₽), свежесть
упала с 86.43 % до 82.27 % — утеплённый кузов без рефа держит груз лучше
обычного тента, но хуже рефрижератора, поэтому система «выбирает
математически наименьший убыток».

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
`shipped_kg = 3125.0`, `unmet_kg = 1050.0`, `total_tco_rub = 37636.26`
(доставка + потери, без штрафов), `unmet_pct = 25.15`,
`avg_freshness_pct = 89.88` против 88.77 под ливнем (без замедления груз
портится меньше): порча 33 820.54 ₽ в ливень против 30 032.93 ₽ в жару.

Множитель грунтовки `k_surface = 1.35` проверяется unit-тестами
(`backend/tests/test_freshness_math.py`) и косвенно в S1: плечо ГАЗона
до Кооператива Боровск (грунтовка, 19.06 км) занимает 32.37 мин — это
`62 км/ч ÷ 1.35 × 1.3`; асфальтовое плечо КАМАЗа до Агро-Рынка (35.82 км)
занимает 39.92 мин — `70 км/ч ÷ 1.3`.

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

Ожидается: первые два числа равны (расхождение ≤ 0.05), третье ≈ 4 175,
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
2. После входа видна карта с 7 маркерами и вкладки «Заказы», «Машины и склады», «Расчёт».
3. Вкладка «Расчёт» → «Рассчитать поставки».

Ожидается: предупреждения и таблица маршрутов появляются меньше чем за 1,5 с
(на дев-машине ~0,2 с): 2 машины (Volvo — 4 остановки, ГАЗон — 5), всего
9 остановок; на карте — две полилинии разных цветов. Плиток-метрик на вкладке
нет — затраты и сохранность смотрите в XLSX или на печати.

**UI-2. Грунтовка в плане**

В таблице маршрутов у покупателей с `road_type: dirt` (Боровск, Таруса) есть отметка
«грунтовка» с иконкой дороги; на карте такие точки окрашены в цвет грунтовки,
а в легенде под картой есть соответствующая подпись. В карточке объекта,
выпадающей при наведении на маркер, тип дороги текстом не выводится.

**UI-3. Недоступная грунтовка**

```bash
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/2
curl -s -H "$U" -X PATCH -H 'Content-Type: application/json' -d '{"status":"broken"}' $B/erp/trucks/3
```

Пересчитайте план в UI. Ожидается: замечания «Не в работе: 2 — в расчёте
не участвуют», «Не удалось привезти 1050 кг…» и три «К этой точке не проехать:
нужна машина, которая может ехать по грунтовке» с чипами «Заказ №5/6/9»;
в блоке «На что обратить внимание» — «Ни одной машины, которая может ехать
по грунтовке…»; в маршрутном листе затраты на доставку ниже, чем при
полном автопарке, не привезли `1 050 кг`.
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

1. Посчитайте план на вкладке «Расчёт».
2. На вкладке «Заказы» отметьте любую заявку доставленной; на вкладке
   «Машины и склады» переведите машину в `broken`.
3. Вернитесь на «Расчёт»: план остался на экране, но появился блок
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

Ожидается порядок листов: `Сводка`, `Рейсы`, `Аналитика`, `Замечания`,
`Заказы`, `Машины`, `Склады и остатки`, затем по одному листу
`Рейс N <номер>` на каждую машину. Диаграмм и символов валюты в файле нет,
деньги подписаны как «руб.»:

* в сводке — выручка, маржа, показатели (затраты, потери руб./кг/%, прибыль,
  сохранность, привезли/не привезли, рейсы, загрузка) и краткая таблица рейсов;
* в «Рейсах» — оснащение (рефрижератор/утепление/грунт), вместимость, отгружено,
  загрузка %, остановок, пробег, время, выручка, потери (кг/руб.), стоимость,
  маржа, сохранность; строка `Итого`;
* в «Аналитике» — по строке на остановку (заказ, покупатель с адресом, дорога,
  культура, склад, свежесть партии, цена, выручка, плечо и время плеча, ETA,
  сохранность, потери кг/руб., стоимость плеча, маржа, этап) и строка `Итого`;
* в «Замечаниях» — недовоз, остановки ниже порога свежести, недогруженные рейсы
  или строка «Замечаний нет»;
* в «Заказах» — таблица сайта: `№ / Покупатель / Адрес / Культура / Заказано, кг /
  Доставлено, кг / Остаток, кг / Цена, руб./кг / Дорога / Этап` (9 строк);
* в «Машинах» — `Машина / Госномер / База / Вместимость, кг / Цена за км, руб. /
  Выезд, руб. / Оснащение / Статус` (3 строки);
* в «Складах и остатках» — матрица `Склад / Адрес / <культура, кг>… / Итого, кг`
  с итоговой строкой по культурам;
* в листе рейса — шапка (машина, склад, оснащение, вместимость, загрузка, пробег,
  стоимость, выручка, потери, маржа) и таблица остановок
  `№ / Заказ / Покупатель / Урожай / Отгружено, кг / Расстояние, км / В пути, мин /
  Сохранность, % / Стоимость, руб. / Статус`, затем строка `Итого`.

Контроль сходимости: сумма `shipped_kg` по листам рейсов совпадает с
`metrics.shipped_kg`; сумма выручки в «Аналитике» = `metrics.expected_net_profit_rub`
+ `metrics.total_tco_rub`; сумма потерь руб. ≈ `metrics.total_spoilage_loss_rub`,
сумма стоимости плеч = `metrics.total_trip_cost_rub`.

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

Ожидается `['Сводка', 'Рейсы', 'Аналитика', 'Замечания', 'Рейс 1 ...', ...]`
и строка заголовков `['Показатель', 'Значение']` — колонок сравнения
«Было / Стало» в сводке нет; заявка `1` не появляется ни в «Аналитике»,
ни в листах рейсов нового расчёта.

### 10.4 Негативные сценарии

```bash
curl -s -o /dev/null -w 'no pin:  %{http_code}\n' $B/export/run/1/xlsx
curl -s -w '\nunknown: %{http_code}\n' -H "$U" $B/export/run/9999/xlsx
```

Ожидается `401` (`code: unauthorized`) без PIN и `404`
(`code: not_found`, `detail: Расчёт №9999 не найден`) для
несуществующего расчёта. Если все машины не в работе, экспорт всё равно отдаёт
рабочий файл с листами `Сводка`, `Рейсы`, `Аналитика`, `Замечания` (без листов
рейсов): в сводке `Не привезли, кг` > 0, в «Замечаниях» — строка про недовоз.

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

Ожидается 6 листов: `Сводка`, `Рейсы`, `Аналитика`, `Замечания`,
`Рейс 1 <госномер>`, `Рейс 2 …`. В сводке — `Машин = 2` и метрики сохранённого
расчёта; в «Рейсах» — по строке на машину и `Итого`; в «Аналитике» — по строке
на каждую остановку.

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

Ожидаемые числа: 2 блока машин и 9 строк остановок (веса зависят от живой
погоды режима `normal`; на пресете `heavy_rain` — 1 625 и 2 550 кг),
суммарно 4 175 кг.

### 10.7 Ручное создание справочников (frontend)

Раньше данные приходили только из seed, теперь их можно добавлять из интерфейса.
Перед сценарием: `reset-demo`.

**UI-1. Библиотека товаров**

Вкладка «Товары» → кнопка «Товар»: код, название, потеря свежести за час,
оптимальная температура, себестоимость. После сохранения строка появляется в
таблице, а товар становится доступен в заказах и партиях. Повторный код →
сообщение «Товар не добавлен: проверьте код (он должен быть уникальным)».

**UI-2. Магазин**

Вкладка «Заказы» → «Магазин»: название, адрес, тип подъезда (асфальт/грунтовка),
широта и долгота. Точка сразу появляется на карте, а магазин — в списке заказов.

**UI-3. Заказ**

Вкладка «Заказы» → «Заказ»: выбор магазина и товара, объём в кг, цена ₽/кг и
неустойка за недовоз. Новый заказ создаётся в статусе «В плане» и участвует в
следующем расчёте.

**UI-4. Машина**

Вкладка «Машины и склады» → «Машина»: название, госномер, база (склад),
вместимость, скорость, ₽/км, фикс за рейс и оснащение (рефрижератор,
изотермический кузов, допуск к грунтовке). Госномер нормализуется в верхний
регистр; повтор номера → сообщение о дубликате.

**UI-5. Партия на складе**

Вкладка «Машины и склады» → «Партия»: склад, товар, доступно кг и свежесть
партии (0,5…1). Диалог заранее перечисляет занятые пары «склад — товар»;
попытка продублировать пару возвращает «Партия не добавлена: возможно, у этого
склада уже есть партия такого товара» (сервер отвечает 409).

**Проверка через API**

```bash
curl -s -H "$U" -X POST -H 'Content-Type: application/json' \
  -d '{"code":"blueberry","name":"Голубика","base_spoilage_rate":0.09,"optimal_temp_c":4,"base_cost_rub":420}' \
  $B/erp/products    # 201; повтор с тем же кодом → 409
```

Все создающие вызовы требуют `X-Access-Pin` (без него 401).

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
