# User Flow & State Transitions

## 1. Диаграмма состояний экрана и сессии (State Diagram)

```mermaid
stateDiagram-v2
    [*] --> LandingPage: Открытие сайта (/)
    LandingPage --> PinAuthScreen: Клик «Войти в терминал диспетчера» (/login)
    
    state PinAuthScreen {
        [*] --> TypingPin: Ввод цифр (0..5 точек)
        TypingPin --> AutoVerify: Введена 6-я цифра
        AutoVerify --> ErrorShake: PIN неверный (401)
        ErrorShake --> TypingPin: Автоочистка поля (300ms)
    }

    AutoVerify --> MainWorkspace: PIN верный (200 OK, сохранение роли user/admin)
    
    state MainWorkspace {
        [*] --> ErpSetup: Загрузка складов, фур, точек и погоды
        ErpSetup --> BaselineSolved: Клик «Рассчитать поставки» (< 2 сек)
        BaselineSolved --> WhatIfEvent: Поломка машины / Смена цены / Смена погоды / Отметка «Доставлено»
        WhatIfEvent --> RecalculatedComparison: Авто-пересчёт остатка маршрутов
        RecalculatedComparison --> WhatIfEvent: Новое изменение
        BaselineSolved --> ExportSheet: Выгрузка PDF / XLSX
        RecalculatedComparison --> ExportSheet: Выгрузка обновлённых PDF / XLSX
    }
```

## 2. Пошаговая последовательность (Sequence Diagram: Расчёт и «Что, если»)

```mermaid
sequenceDiagram
    actor Logist as Логист-диспетчер
    participant SPA as Vue 3 + Vuetify 4 SPA
    participant API as FastAPI Backend
    participant DB as SQLite (app.db)
    participant Weather as Open-Meteo API
    participant Solver as Bio-Logistics Solver

    Logist->>SPA: Вводит 6 цифр PIN-кода (заполняются 6 точек)
    SPA->>API: POST /api/v1/auth/verify-pin (X-Access-Pin)
    API-->>SPA: 200 OK { role: "admin" | "dispatcher" }

    SPA->>API: GET /api/v1/erp/state + GET /api/v1/weather/current
    API->>Weather: Запрос погоды по Калужской области (Обнинск)
    Weather-->>API: Температура, осадки
    API->>DB: Чтение складов, остатков, клиентов, фур
    API-->>SPA: Полный стейт ERP + метеосводка

    Logist->>SPA: Нажимает «Рассчитать поставки» (Базовый план)
    SPA->>API: POST /api/v1/solver/optimize { mode: "baseline" }
    API->>DB: Чтение RouteCache (или дозапрос Mapbox)
    API->>Solver: Расчёт TCO (учёт рефов, грунтовок, скорости порчи)
    Solver-->>API: Оптимальные рейсы, метрики TCO, полилинии
    API->>DB: Сохранение SimulationRun (id=1, baseline)
    API-->>SPA: JSON с маршрутами и экономикой (< 2 сек)
    SPA->>Logist: Отрисовка маршрутов на Mapbox + сводка TCO

    Note over Logist,SPA: Стресс-сценарий «Что, если» в реальном времени
    Logist->>SPA: Отмечает Точку #1 «Доставлено», ломает Фуру #1, меняет цену Клиента #3
    SPA->>API: POST /api/v1/solver/optimize { baseline_run_id: 1, overrides: ... }
    API->>Solver: Заморозка доставленных точек, перераспределение остатка на живые машины
    Solver-->>API: Новый план + расчёт дельты «Было / Стало»
    API-->>SPA: Новый план + объект ComparisonDelta
    SPA->>Logist: Отрисовка новых маршрутов + таблица «Было / Стало»

    Logist->>SPA: Нажимает «Экспорт маршрутного листа (PDF / XLSX)»
    alt Экспорт в PDF
        SPA->>Logist: Открывает печатный представление @media print (window.print())
    else Экспорт в XLSX
        SPA->>API: GET /api/v1/export/run/{run_id}/xlsx
        API-->>SPA: StreamingResponse (.xlsx файл)
    end
```

## 3. Обработка негативных пользовательских сценариев
1. **Неверный PIN-код:**
   * При вводе 6-й цифры кружки-индикаторы окрашиваются в цвет `error` (`#EF5350`), ряд точек выполняет горизонтальную CSS-анимацию `shake` (300 мс), после чего массив введённых символов автоматически очищается и фокус остаётся готовым к повторному набору с клавиатуры.
2. **Назначение еврофуры на грунтовку вручную / нехватка проходимых машин:**
   * Если все вездеходные среднетоннажники выведены из строя (`status = 'broken'`), а у клиента в селе подъезд `dirt`, солвер оставляет заявку этого клиента в статусе `Unmet Demand`, не назначая туда еврофуру, и выводит в блоке предупреждений: *«Точка [Название] недоступна: требуется транспорт с допуском к грунтовым дорогам»*.
3. **Экстремальная жара без рефрижератора:**
   * Если логист включает пресет «Жара +35°C» и ломает все машины с рефрижераторами, система сравнивает потери от порчи клубники в обычном тентованном кузове со штрафом за недовоз и выбирает математически наименьший убыток, наглядно подсвечивая падение средней свежести в таблице «Было / Стало».
