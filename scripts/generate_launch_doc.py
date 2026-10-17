#!/usr/bin/env python3
"""Generate the canonical local and production launch guide."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "docs" / "launch.config.json"
OUTPUT_PATH = ROOT / "docs" / "LAUNCH.md"


def load_config() -> dict[str, object]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def render(config: dict[str, object]) -> str:
    backend = config["backend"]
    frontend = config["frontend"]
    production = config["production"]
    ci = config["ci"]
    assert isinstance(backend, dict)
    assert isinstance(frontend, dict)
    assert isinstance(production, dict)
    assert isinstance(ci, dict)

    ci_variables = "\n".join(f"- `{name}`" for name in ci["variables"])
    ci_secrets = "\n".join(f"- `{name}`" for name in ci["secrets"])
    ci_optional = "\n".join(f"- `{name}`" for name in ci["optional_secrets"])

    return f'''# Запуск AgroLogistix

> Этот файл сгенерирован из `docs/launch.config.json` командой
> `python scripts/generate_launch_doc.py`. Не редактируйте его вручную.
>
> Проект запускается напрямую на хосте: backend работает через `uvicorn`,
> frontend в разработке через Vite, а production-раздача выполняется
> standalone Nginx и `systemd`.

## Требования

- Python {config["python"]}
- Node.js {config["node"]} и npm
- `uv`
- Nginx нужен только для production-развёртывания

## Первый запуск

Из корня репозитория:

```bash
uv sync --directory backend --extra dev
npm ci --prefix frontend
```

Локальные PIN по умолчанию:

- dispatcher: `{backend["user_pin"]}`
- admin: `{backend["admin_pin"]}`

В production `USER_ACCESS_PIN` и `ADMIN_ACCESS_PIN` должны быть заданы явно и
отличаться друг от друга, иначе backend не стартует (`app_env=production`).
Дефолтные значения `202601`/`999999` запускаются, но пишут предупреждение в
лог — их стоит сменить для публичного стенда.

## Запуск backend

В отдельном терминале:

```bash
uv run --directory backend uvicorn {backend["module"]} \\
  --app-dir backend \\
  --host {backend["host"]} \\
  --port {backend["dev_port"]} \\
  --reload
```

Проверка:

```bash
curl -i http://{backend["host"]}:{backend["dev_port"]}{backend["health_path"]}
curl -i -X POST \\
  -H 'X-Access-Pin: {backend["user_pin"]}' \\
  http://{backend["host"]}:{backend["dev_port"]}/api/v1/auth/verify-pin
```

SQLite создаётся в `{backend["database_path"]}`. Режим WAL включается приложением.

## Запуск frontend

В отдельном терминале:

```bash
npm run dev --prefix frontend
```

Откройте <http://{frontend["host"]}:{frontend["dev_port"]}>.
Vite проксирует запросы `/api` на backend `http://localhost:{backend["dev_port"]}`.

### Токен Mapbox (карта)

`VITE_MAPBOX_PUBLIC_TOKEN` — переменная **этапа сборки**: Vite встраивает её в
JS-бандл при `npm run build`, поэтому на сервере фронтовый `.env` не нужен.

- локально: `frontend/.env` со строкой `VITE_MAPBOX_PUBLIC_TOKEN=pk...`;
- в CI: Repository Variable `VITE_MAPBOX_PUBLIC_TOKEN`, прокинутая в шаги сборки фронтенда;
- после смены токена фронтенд нужно **пересобрать**.

Секретный `MAPBOX_SECRET_TOKEN` (серверные запросы к Mapbox) хранится только в
`{production["backend_install_directory"]}/.env` и никогда не попадает во фронтенд.
Public-токен ограничьте URL-ами домена и `http://localhost:{frontend["dev_port"]}/*` в
кабинете Mapbox.

Матрица дорог строится по одному запросу на пару точек, поэтому у Directions
отдельный таймаут `MAPBOX_TIMEOUT_SEC` (по умолчанию `8`): с общим
`EXTERNAL_API_TIMEOUT_SEC=1.5` расчёт уходил в haversine-фолбэк и рисовал прямые
линии вместо дорог.

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

1. На сервере код размещается в `{production["backend_install_directory"]}`.
2. В `{production["backend_install_directory"]}/backend` выполняется `uv sync --locked --no-dev`.
3. Backend запускается одним процессом `uvicorn` через
   `systemd`-юнит `{production["backend_service_name"]}`.
4. Перед перезапуском `deploy/deploy.sh` вызывает
   `deploy/sync-backend-env.sh`, который обновляет `{production["backend_env_file"]}`
   (`APP_ENV`, `USER_ACCESS_PIN`, `ADMIN_ACCESS_PIN`, `MAPBOX_SECRET_TOKEN`) и
   сохраняет остальные строки файла: значения приходят из GitHub
   `vars`/`secrets`, а `systemd` читает их через `EnvironmentFile`.
5. GitHub Actions собирает frontend командой `npm ci && npm run build`.
6. Каталог `{production["frontend_build_directory"]}` копируется в
   `{production["frontend_web_root"]}`.
7. Standalone Nginx раздаёт статику, делает SPA fallback на `index.html` и
   проксирует `/api/` на `127.0.0.1:{backend["dev_port"]}`.
8. Nginx завершает TLS сертификатом Let's Encrypt из
   `{production["tls_certificate_dir"]}`; HTTP редиректится на HTTPS, кроме
   `/health` и ACME-challenge.

Пример backend-юнита:

```ini
[Unit]
Description=AgroLogistix FastAPI backend
After=network.target

[Service]
User=agrologistix
WorkingDirectory={production["backend_install_directory"]}
EnvironmentFile={production["backend_env_file"]}
ExecStart={production["backend_install_directory"]}/backend/.venv/bin/uvicorn {backend["module"]} --host 127.0.0.1 --port {backend["dev_port"]} --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

После установки юнита:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now {production["backend_service_name"]}
sudo systemctl status {production["backend_service_name"]}
```

## HTTPS (Let's Encrypt)

Конфиг `{production["nginx_config"]}` слушает `80` и `443`, а сертификат берётся
из `{production["tls_certificate_dir"]}`. Первичный выпуск выполняется один раз
с локальной машины:

```bash
DEPLOY_HOST=<host> \
DEPLOY_USER=<user> \
DEPLOY_DOMAIN=<domain> \
DEPLOY_WEB_ROOT={production["frontend_web_root"]} \
DEPLOY_SSH_KEY_PATH=<key> \
{production["https_setup_command"]}
```

Скрипт `deploy/setup-https.sh` идемпотентен и выполняет шаги:

1. ставит HTTP-only bootstrap-конфиг
   `{production["nginx_bootstrap_config"]}` (нужен, чтобы ACME ответил до
   появления сертификата);
2. выпускает сертификат: `certbot certonly --webroot -w {production["frontend_web_root"]} -d <domain>`;
3. ставит TLS-конфиг `{production["nginx_config"]}` и перезагружает Nginx;
4. включает `{production["tls_renewal_timer"]}` и deploy-hook, который
   перезагружает Nginx после каждого продления.

Проверка:

```bash
curl -I https://<domain>/health
curl -I http://<domain>/health   # 301 на https
certbot renew --dry-run --no-random-sleep-on-renew
```

`deploy/deploy.sh` требует `DEPLOY_DOMAIN` и перед копированием конфига
проверяет наличие сертификата: если его нет, деплой останавливается с
подсказкой запустить bootstrap.

Если домен проксируется через Cloudflare, режим SSL/TLS должен быть
`Full` или `Full (strict)`. В режиме `Flexible` Nginx получает HTTP-запросы,
и редирект `http → https` создаст цикл; в этом случае включите `Full (strict)`
после выпуска сертификата.

## Деплой через GitHub Actions

Workflow `{ci["workflow"]}` выполняет три джобы: `backend-checks`,
`frontend-checks` и `deploy`. Джоба `deploy` запускается только для
ветки `main` (или вручную через `workflow_dispatch`) и выполняет:

```bash
{ci["deploy_command"]}
```

Скрипт собирает frontend, синхронизирует backend и `frontend/dist` по SSH,
перезапускает сервис и проверяет health-эндпоинты.

### Repository Variables

{ci_variables}

### Repository Secrets

{ci_secrets}

Опционально (когда появится реальный ключ):

{ci_optional}

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
'''


def main() -> int:
    check_only = "--check" in sys.argv
    expected = render(load_config())
    if check_only:
        actual = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if actual != expected:
            print(f"{OUTPUT_PATH} is out of date; run python scripts/generate_launch_doc.py")
            return 1
        return 0

    OUTPUT_PATH.write_text(expected, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
