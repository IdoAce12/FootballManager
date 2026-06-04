# Football Manager (FC26)

Full-stack football management game: FastAPI backend + React (Vite + TypeScript) frontend.

## Project structure

```
FootballManager/
├── football_manager_engine/   # Backend API (Python / FastAPI)
├── frontend/                  # Dashboard UI (React + Vite)
└── FC26_20250921.csv          # Player dataset (~18k players)
```

## Requirements

- Python 3.10+
- Node.js 18+

## Backend

```bash
cd football_manager_engine
pip install -r requirements.txt
python -m uvicorn api:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

Optional: set `VITE_API_URL=http://localhost:8000` in `frontend/.env`.

## License

Private project — IdoAce12.
