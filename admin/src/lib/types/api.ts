export type ApiJsonValue =
  | string
  | number
  | boolean
  | null
  | ApiJsonValue[]
  | { [key: string]: ApiJsonValue };

export type ApiMetadata = {
  request_id: string;
  served_at: string;
} & Record<string, ApiJsonValue>;

export interface ApiResponse<T, M extends ApiMetadata = ApiMetadata> {
  status: number;
  error: boolean;
  message: string;
  data: T;
  meta: M;
}

export type PaginationMeta = ApiMetadata & {
  current_page: number;
  total_pages: number;
  total_count: number;
  page_size: number;
  has_more: boolean;
}

export interface User {
  id: string;
  fullname: string | null;
  telnumber: string | null;
  location: string | null;
  age: number | null;
  email: string | null;
  is_admin: boolean;
  is_active: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Question {
  id: string;
  question: string;
  response: string | null;
  request_type: string | null;
  created_at: string;
  user_fullname: string | null;
  user_telnumber: string | null;
}

export interface ActivityLog {
  id: string;
  action: string;
  target_type: string;
  target_id: string | null;
  details: string | null;
  created_at: string;
  admin_name: string | null;
}

export interface OverviewStats {
  total_users: number;
  active_users: number;
  inactive_users: number;
  total_admins: number;
  total_questions: number;
  new_users_7d: number;
  new_users_30d: number;
  questions_7d: number;
  questions_30d: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
}

export interface MfaChallengeResponse {
  challenge_token: string;
  expires_in_seconds: number;
}

export interface MfaSetupResponse {
  secret: string;
  otpauth_uri: string;
  enroll_challenge_token: string;
  expires_in_seconds: number;
}

export interface MfaEnrollmentResponse extends LoginResponse {
  recovery_codes: string[];
}

export interface FeedbackAnswer {
  id: string;
  pseudo_id: string;
  question_key: string;
  rating: number | null;
  answer: string | null;
  created_at: string;
}

export interface FeedbackAggregate {
  question_key: string;
  count: number;
  rated_count: number;
  average_rating: number | null;
  ratings: Record<string, number>;
}

export interface FeedbackPage {
  items: FeedbackAnswer[];
  aggregates: FeedbackAggregate[];
}
