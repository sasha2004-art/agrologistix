# Запуск AgroLogistix

> Этот файл сгенерирован из `docs/launch.config.json` командой
> `python scripts/generate_launch_doc.py`. Не редактируйте его вручную.
>
> Проект запускается напрямую на хосте: backend работает через `uvicorn`,
> frontend в разработке через Vite, а production-раздача выполняется
> standalone Nginx и `systemd`.

## Требования

- Python 3.12
- Node.js 22 и npm
- `uv`
- Nginx нужен только для production-развёртывания

## Первый запуск

Из корня репозитория:

```bash
uv sync --directory backend --extra dev
npm ci --prefix frontend
```

Локальные PIN по умолчанию:

- dispatcher: `202601`
- admin: `999999`

## Запуск backend

В отдельном терминале:

```bash
uv run --directory backend uvicorn app.main:app \
  --app-dir backend \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

Проверка:

```bash
curl -i http://127.0.0.1:8000/api/v1/health
curl -i -X POST \
  -H 'X-Access-Pin: 202601' \
  http://127.0.0.1:8000/api/v1/auth/verify-pin
```

SQLite создаётся в `./data/app.db`. Режим WAL включается приложением.

## Запуск frontend

В отдельном терминале:

```bash
npm run dev --prefix frontend
```

Откройте <http://127.0.0.1:5173>.
Vite проксирует запросы `/api` на backend `http://localhost:8000`.

## Проверки

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

## Production-схема на хосте

1. На сервере код размещается в `/opt/agrologistix`.
2. В `/opt/agrologistix/backend` выполняется `uv sync --locked --no-dev`.
3. Backend запускается одним процессом `uvicorn` через
   `systemd`-юнит `agrologistix-backend.service`.
4. GitHub Actions собирает frontend командой `npm ci && npm run build`.
5. Каталог `frontend/dist` копируется в
   `/var/www/agrologistix`.
6. Standalone Nginx раздаёт статику, делает SPA fallback на `index.html` и
   проксирует `/api/` на `127.0.0.1:8000`.

Пример backend-юнита:

```ini
[Unit]
Description=AgroLogistix FastAPI backend
After=network.target

[Service]
User=agrologistix
WorkingDirectory=/opt/agrologistix
EnvironmentFile=/opt/agrologistix/.env
ExecStart=/opt/agrologistix/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

После установки юнита:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agrologistix-backend.service
sudo systemctl status agrologistix-backend.service
```

## Деплой через GitHub Actions

Workflow `.github/workflows/ci-deploy.yml` выполняет три джобы: `backend-checks`,
`frontend-checks` и `deploy`. Джоба `deploy` запускается только для
ветки `main` (или вручную через `workflow_dispatch`) и выполняет:

```bash
bash deploy/deploy.sh
```

Скрипт собирает frontend, синхронизирует backend и `frontend/dist` по SSH,
перезапускает сервис и проверяет health-эндпоинты.

### Repository Variables

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_APP_DIR`
- `DEPLOY_WEB_ROOT`
- `DEPLOY_SERVICE`
- `DEPLOY_DOMAIN`
- `APP_ENV`

### Repository Secrets

- `DEPLOY_SSH_KEY`
- `DEPLOY_SSH_KNOWN_HOSTS`
- `USER_ACCESS_PIN`
- `ADMIN_ACCESS_PIN`

Опционально (когда появится реальный ключ):

- `MAPBOX_SECRET_TOKEN`

`DEPLOY_SSH_KEY` — приватный deploy-ключ, публичная часть которого
добавлена в `/root/.ssh/authorized_keys` на сервере.
`DEPLOY_SSH_KNOWN_HOSTS` — вывод `ssh-keyscan <host>`.

## Обновление документа

После изменения команд, портов, путей или production-схемы обновите
`docs/launch.config.json`, затем выполните:

```bash
python scripts/generate_launch_doc.py
```

CI проверяет, что `docs/LAUNCH.md` совпадает с результатом генерации.
