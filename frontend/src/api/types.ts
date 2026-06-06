/**
 * Strongly-typed mirror of the FastAPI backend's Pydantic response models.
 * Keeping these in lockstep with `api.py` gives us a single source of truth
 * for the JSON contract across the whole frontend.
 */

export interface StatusResponse {
  season_year: number;
  current_week: number;
  total_matchdays: number;
  season_complete: boolean;
  /** Server has a previewed matchday that must be confirmed before the calendar advances. */
  pending_matchday: boolean;
  club_id: number;
  club_name: string;
  league_name: string;
  league_position: number;
  transfer_budget: number;
  transfer_budget_label: string;
  weekly_wage_bill: number;
  points: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  squad_overall: number;
}

export interface PlayerSummary {
  player_id: number;
  name: string;
  long_name: string;
  age: number;
  nationality: string;
  position: string;
  positions: string[];
  overall: number;
  potential: number;
  market_value: number;
  market_value_label: string;
  wage_eur: number;
  stamina: number;
  fitness: number;
  form: number;
  morale: number;
  sharpness: number;
  pace: number;
  shooting: number;
  passing: number;
  dribbling: number;
  defending: number;
  physic: number;
  goals: number;
  assists: number;
  goals_scored: number;
  assists_given: number;
  clean_sheets: number;
  appearances: number;
  average_rating: number;
  is_injured: boolean;
  injured_for_matchdays: number;
  contract_until: number;
}

export interface LineupSlot {
  slot_index: number;
  position: string;
  player_id: number | null;
  player_name: string | null;
  overall: number | null;
  potential: number | null;
}

export interface SquadResponse {
  club_id: number;
  club_name: string;
  formation: string;
  squad_overall: number;
  attack_rating: number;
  midfield_rating: number;
  defence_rating: number;
  goalkeeper_rating: number;
  player_count: number;
  lineup: LineupSlot[];
  players: PlayerSummary[];
}

export interface LineupUpdateRequest {
  formation?: string | null;
  starting_xi: number[];
}

export interface ScoutTarget {
  player_id: number;
  name: string;
  age: number;
  nationality: string;
  position: string;
  overall: number;
  potential: number;
  growth_potential: number;
  market_value: number;
  market_value_label: string;
  wage_eur: number;
  club_name: string | null;
}

export interface WonderkidResponse {
  count: number;
  wonderkids: ScoutTarget[];
}

export interface ScoutSearchParams {
  name?: string;
  position?: string;
  min_age?: number;
  max_age?: number;
  min_ovr?: number;
  max_ovr?: number;
  min_pot?: number;
  max_pot?: number;
  limit?: number;
}

export interface SearchResponse {
  filters_applied: Record<string, string | number>;
  count: number;
  results: ScoutTarget[];
}

export interface LeagueOption {
  league_id: number;
  league_name: string;
  level: number;
  club_count: number;
}

export interface ClubOption {
  club_team_id: number;
  club_name: string;
  overall: number;
  transfer_budget_label: string;
}

export interface SetupRequest {
  manager_name: string;
  league_id: number;
  club_team_id: number;
}

export interface SessionResponse {
  initialized: boolean;
  manager_name: string | null;
  league_id: number | null;
  league_name: string | null;
  club_id: number | null;
  club_name: string | null;
  squad_overall: number | null;
  transfer_budget_label: string | null;
}

export interface SignRequest {
  player_id: number;
  fee?: number | null;
  weekly_wage?: number | null;
  contract_years?: number;
}

export interface SignResponse {
  success: boolean;
  message: string;
  player_name: string;
  from_club: string;
  to_club: string;
  fee: number;
  fee_label: string;
  weekly_wage: number;
  remaining_budget: number;
  remaining_budget_label: string;
}

export interface SellRequest {
  player_id: number;
}

export interface SellResponse {
  success: boolean;
  message: string;
  player_name: string;
  buyer_club: string;
  fee: number;
  fee_label: string;
  multiplier_pct: number;
  market_value: number;
  market_value_label: string;
  remaining_budget: number;
  remaining_budget_label: string;
  squad_size: number;
}

export interface IncomingTransferBid {
  player_id: number;
  player_name: string;
  player_overall: number;
  bidding_club: string;
  fee: number;
  fee_label: string;
  market_value: number;
  market_value_label: string;
}

export interface NextSeasonResponse {
  success: boolean;
  message: string;
  previous_season_year: number;
  new_season_year: number;
  league_position: number;
  budget_bonus: number;
  budget_bonus_label: string;
  new_transfer_budget: number;
  new_transfer_budget_label: string;
  total_matchdays: number;
  promoted: boolean;
  promotion_from_league: string | null;
  promotion_to_league: string | null;
  new_league_id: number | null;
  new_league_name: string | null;
  new_league_level: number | null;
  matchday_win_reward: number;
  matchday_draw_reward: number;
  season_status: string;
}

export interface AcceptBidRequest {
  player_id: number;
  fee: number;
}

export interface AcceptBidResponse {
  success: boolean;
  message: string;
  player_name: string;
  fee: number;
  fee_label: string;
  remaining_budget: number;
  remaining_budget_label: string;
  squad_size: number;
}

export interface CareerSeasonRecord {
  season_year: number;
  club_name: string;
  league_name: string;
  final_position: number;
  status: string;
}

export interface CareerProfileResponse {
  manager_name: string;
  bio: string;
  history: CareerSeasonRecord[];
  trophy_count: number;
}

export interface MatchEventModel {
  minute: number;
  type: string;
  team: string;
  description: string;
  player: string | null;
}

export interface TeamStatsModel {
  club_id: number;
  name: string;
  goals: number;
  shots: number;
  shots_on_target: number;
  possession_pct: number;
  expected_goals: number;
  yellow_cards: number;
  red_cards: number;
}

export interface OtherResultModel {
  home: string;
  away: string;
  home_goals: number;
  away_goals: number;
  scoreline: string;
}

export interface StandingRow {
  position: number;
  club_id: number;
  club_name: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goal_difference: number;
  points: number;
}

export interface SimulateResponse {
  committed: boolean;
  pending_confirmation: boolean;
  matchday: number;
  total_matchdays: number;
  season_complete: boolean;
  user_match_played: boolean;
  scoreline: string | null;
  home_stats: TeamStatsModel | null;
  away_stats: TeamStatsModel | null;
  events: MatchEventModel[];
  other_results: OtherResultModel[];
  standings: StandingRow[];
}

/** Optional per-player development payloads (ignored safely if absent). */
export interface DevelopmentUpdateModel {
  player_id: number;
  player_name: string;
  overall_delta: number;
  potential_delta: number;
}

export interface ConfirmMatchdayResponse {
  committed: boolean;
  matchday: number;
  total_matchdays: number;
  season_complete: boolean;
  standings: StandingRow[];
  match_reward: number;
  match_reward_label: string;
  match_reward_outcome: 'win' | 'draw' | 'loss' | 'none' | string;
  continental_match_played?: boolean;
  continental_match_reward?: number;
  continental_match_reward_label?: string;
  continental_match_reward_outcome?: 'win' | 'draw' | 'loss' | 'none' | string;
  transfer_budget: number;
  transfer_budget_label: string;
  incoming_bid?: IncomingTransferBid | null;
  development?: DevelopmentUpdateModel[];
}

export interface ContinentalFixtureModel {
  matchday: number;
  league_matchday: number | null;
  home_id: number;
  home_name: string;
  away_id: number;
  away_name: string;
  stage: string;
  group_name: string | null;
  home_goals: number | null;
  away_goals: number | null;
  is_played: boolean;
}

export interface ContinentalGroupStandingRow {
  position: number;
  club_id: number;
  club_name: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goal_difference: number;
  points: number;
}

export interface ContinentalGroupModel {
  group_name: string;
  standings: ContinentalGroupStandingRow[];
}

export interface ContinentalBracketMatchModel {
  matchday: number;
  stage: string;
  home_id: number;
  home_name: string;
  away_id: number;
  away_name: string;
  home_goals: number | null;
  away_goals: number | null;
  winner_id: number | null;
  winner_name: string | null;
}

export interface ContinentalCupResponse {
  name: string;
  season_year: number;
  active: boolean;
  phase: string;
  qualified: boolean;
  current_matchday: number;
  total_matchdays: number;
  champion_club_id: number | null;
  champion_club_name: string | null;
  groups: ContinentalGroupModel[];
  fixtures: ContinentalFixtureModel[];
  bracket: ContinentalBracketMatchModel[];
  schedule_anchors: number[];
}
