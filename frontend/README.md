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
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_API_AUTH_TOKEN=
VITE_KAKAO_MAP_APPKEY=
```

The voice assistant uses `POST /api/upload`, which returns the backend's frontend-compatible response shape. The default bus board uses `GET /api/bus/default`.

For deployed browser builds, prefer an HTTPS backend URL. Microphone permissions and mixed-content rules can block voice upload when the page is served from HTTPS but the API is HTTP.
