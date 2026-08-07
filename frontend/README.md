# BITBOX Frontend

React + Vite frontend for the BITBOX bus information display and voice route assistant.

## Run

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Environment

Create `frontend/.env.local` from `frontend/.env.example`.

```env
VITE_API_BASE_URL=
VITE_API_AUTH_TOKEN=
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000
VITE_KAKAO_MAP_APPKEY=
```

The voice assistant uses `POST /api/upload`, and typed destinations use `POST /api/route`. Both return the same frontend response shape. The default bus board uses `GET /api/bus/default`.

During local development, Vite forwards `/api` to `VITE_DEV_PROXY_TARGET`. In production, leave `VITE_API_BASE_URL` empty when the frontend and `/api` share one HTTPS origin, or set an explicit HTTPS API URL. `APP_ENV=prod` also requires a backend `API_AUTH_TOKEN`, a matching `VITE_API_AUTH_TOKEN`, and restricted `CORS_ALLOWED_ORIGINS`.
