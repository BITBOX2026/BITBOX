# BITBOX Project Structure

This branch keeps the backend and frontend in one repository.

## Backend

Path: `app/`

- `app/main.py`: FastAPI application setup, CORS, router registration, health check.
- `app/api/`: voice upload gateway and API response schemas.
- `app/routers/`: public REST routers such as bus, station, and place APIs.
- `app/services/`: transit, AI, response building, and shared service helpers.
- `app/schemas/`: router-specific Pydantic response models.
- `tests/`: backend tests, including frontend contract checks.

Run locally:

```bash
pip install -r requirements-backend.txt pytest
uvicorn app.main:app --reload
```

Frontend-facing endpoints:

- `GET /api/bus/default`: default bus arrival board data.
- `POST /api/upload`: frontend-compatible voice upload response.
- `POST /api/process`: raw pipeline response for backend/API clients.

## Frontend

Path: `frontend/`

- `frontend/src/api/`: backend API client and endpoint-specific services.
- `frontend/src/app/`: React app and UI components.
- `frontend/src/types/`: shared frontend TypeScript types.
- `frontend/public/`: static assets.

Run locally:

```bash
cd frontend
npm install
npm run dev
```

Build:

```bash
cd frontend
npm run build
```

Frontend environment:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_API_AUTH_TOKEN=
VITE_KAKAO_MAP_APPKEY=
```

Use an HTTPS API URL for deployed browser builds, especially because microphone access and cross-origin requests are sensitive to browser security rules.
