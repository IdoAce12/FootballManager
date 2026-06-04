# FC26 Manager — Web Dashboard (React + TypeScript)

A world-class, dark-themed football-manager command center that consumes the
FC26 FastAPI backend. Built with **Vite + React 18 + TypeScript + Tailwind CSS**.

## Features

| View | Endpoint(s) | Highlights |
| --- | --- | --- |
| **DashboardHeader** (persistent) | `GET /api/status` | Club, manager, matchweek, transfer budget, points + radial **squad-OVR gauge**. |
| **SquadManager** | `GET /api/squad` | Full roster table: Position, Name, Age, OVR, Potential, colour-coded **fitness bar**, Form, Market Value. |
| **ScoutingHub** | `GET /api/scouting/wonderkids`, `GET /api/scouting/search?q=` | Split layout — wonderkids grid + live search (name/position filters), each card with a **SIGN PLAYER** button. |
| **MatchSimTerminal** | `POST /api/matchday/simulate` | Big green launch button, split screen: scores + live table on the left, **animated minute-by-minute commentary stream** on the right. |

Signing a player POSTs to `POST /api/transfers/sign` and shows a notification
toast with the server's response (`deal completed`, `buyer cannot afford the
fee`, …), then instantly refreshes the header budget and squad.

## Architecture

```
src/
├── api/
│   ├── types.ts        # TS mirror of the backend Pydantic models
│   └── client.ts       # typed Axios wrapper (one fn per endpoint)
├── state/
│   ├── GameContext.tsx # global status + version-based cache invalidation
│   ├── ToastProvider.tsx
│   └── useSignPlayer.ts # shared sign action (toast + refresh)
├── components/
│   ├── DashboardHeader.tsx
│   ├── SquadManager.tsx
│   ├── ScoutingHub.tsx
│   ├── MatchSimTerminal.tsx
│   └── ui/             # ProgressBar, OvrGauge
├── lib/format.ts       # colour/format helpers
├── App.tsx             # shell + tab navigation
└── main.tsx            # providers + mount
```

Absolute imports use the `@/*` alias (configured in `vite.config.ts` +
`tsconfig.json`).

## Getting started

```bash
# 1. Make sure the backend is running first (from football_manager_engine/):
#    uvicorn api:app --reload --port 8000

# 2. Install dependencies
cd frontend
npm install

# 3. Start the Vite dev server (http://localhost:5173)
npm run dev
```

The API base URL defaults to `http://localhost:8000`. Override it by copying
`.env.example` to `.env` and editing `VITE_API_URL`.

## Production build

```bash
npm run build     # type-checks then bundles to dist/
npm run preview   # serves the production build locally
```
