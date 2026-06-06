/**
 * Centralised, typed Axios wrapper for the FC26 Manager backend.
 *
 * Every backend endpoint is exposed as a single typed function so components
 * never touch raw URLs or response shapes. Errors are normalised into a
 * consistent `ApiError` so the UI can render meaningful messages.
 */

import axios, { AxiosError, type AxiosInstance } from 'axios';
import type {
  AcceptBidRequest,
  AcceptBidResponse,
  CareerProfileResponse,
  ClubOption,
  LeagueOption,
  ConfirmMatchdayResponse,
  ContinentalCupResponse,
  LineupUpdateRequest,
  NextSeasonResponse,
  SellRequest,
  SellResponse,
  ScoutSearchParams,
  SearchResponse,
  SessionResponse,
  SetupRequest,
  SignRequest,
  SignResponse,
  SimulateResponse,
  SquadResponse,
  StatusResponse,
  WonderkidResponse,
} from '@/api/types';

const LOCAL_DEV_API_URL = 'http://localhost:8000';

/**
 * Resolve the FastAPI base URL:
 * - Production / Vercel: `VITE_API_URL` must be set at build time.
 * - Local dev: falls back to localhost:8000 when the env var is omitted.
 */
export function resolveApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  if (import.meta.env.DEV) {
    return LOCAL_DEV_API_URL;
  }
  return '';
}

export const API_BASE_URL: string = resolveApiBaseUrl();

const http: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000, // matchday simulation can be heavy
  headers: { 'Content-Type': 'application/json' },
});

/** Normalised error type surfaced to the UI layer. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function normaliseError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const axErr = error as AxiosError<{ detail?: string | { msg?: string }[] }>;
    const status = axErr.response?.status ?? 0;
    const detail = axErr.response?.data?.detail;
    let message: string;
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) {
      message = detail[0].msg as string;
    } else if (status === 0) {
      message = API_BASE_URL
        ? `Cannot reach the backend at ${API_BASE_URL}. Check that the API is running and CORS allows this origin.`
        : 'Backend URL is not configured. Set VITE_API_URL in Vercel (or frontend/.env for local builds).';
    } else {
      message = axErr.message;
    }
    return new ApiError(message, status);
  }
  return new ApiError('An unexpected error occurred.', 0);
}

export const gameApi = {
  async getSession(): Promise<SessionResponse> {
    try {
      const { data } = await http.get<SessionResponse>('/api/game/session');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async getLeagues(): Promise<LeagueOption[]> {
    try {
      const { data } = await http.get<LeagueOption[]>('/api/leagues');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async getLeagueClubs(leagueId: number): Promise<ClubOption[]> {
    try {
      const { data } = await http.get<ClubOption[]>(`/api/leagues/${leagueId}/clubs`);
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async setupGame(payload: SetupRequest): Promise<SessionResponse> {
    try {
      const { data } = await http.post<SessionResponse>('/api/game/setup', payload);
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async resetCareer(): Promise<SessionResponse> {
    try {
      const { data } = await http.post<SessionResponse>('/api/game/reset');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async getStatus(): Promise<StatusResponse> {
    try {
      const { data } = await http.get<StatusResponse>('/api/status');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async getContinentalCup(): Promise<ContinentalCupResponse> {
    try {
      const { data } = await http.get<ContinentalCupResponse>('/api/continental');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async getSquad(): Promise<SquadResponse> {
    try {
      const { data } = await http.get<SquadResponse>('/api/squad');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async getWonderkids(limit = 12): Promise<WonderkidResponse> {
    try {
      const { data } = await http.get<WonderkidResponse>('/api/scouting/wonderkids', {
        params: { limit },
      });
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async searchPlayers(params: ScoutSearchParams): Promise<SearchResponse> {
    try {
      const clean: Record<string, string | number> = {};
      for (const [key, val] of Object.entries(params)) {
        if (val !== undefined && val !== null && val !== '') clean[key] = val;
      }
      const { data } = await http.get<SearchResponse>('/api/scouting/search', {
        params: clean,
      });
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async updateLineup(payload: LineupUpdateRequest): Promise<SquadResponse> {
    try {
      const { data } = await http.put<SquadResponse>('/api/squad/lineup', payload);
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async signPlayer(payload: SignRequest): Promise<SignResponse> {
    try {
      const { data } = await http.post<SignResponse>('/api/transfers/sign', payload);
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async sellPlayer(payload: SellRequest): Promise<SellResponse> {
    try {
      const { data } = await http.post<SellResponse>('/api/transfers/sell', payload);
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async advanceNextSeason(): Promise<NextSeasonResponse> {
    try {
      const { data } = await http.post<NextSeasonResponse>('/api/game/next-season');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async getCareerProfile(): Promise<CareerProfileResponse> {
    try {
      const { data } = await http.get<CareerProfileResponse>('/api/career/profile');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async acceptIncomingBid(payload: AcceptBidRequest): Promise<AcceptBidResponse> {
    try {
      const { data } = await http.post<AcceptBidResponse>(
        '/api/transfers/accept-bid',
        payload,
      );
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async simulateMatchday(): Promise<SimulateResponse> {
    try {
      const { data } = await http.post<SimulateResponse>('/api/matchday/simulate');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  async confirmMatchday(): Promise<ConfirmMatchdayResponse> {
    try {
      const { data } = await http.post<ConfirmMatchdayResponse>('/api/matchday/confirm');
      return data;
    } catch (error) {
      throw normaliseError(error);
    }
  },

  /** Alias for confirmMatchday — POST /api/matchday/confirm */
  confirmMatch(): Promise<ConfirmMatchdayResponse> {
    return this.confirmMatchday();
  },
};

export type GameApi = typeof gameApi;
