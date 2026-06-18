export type ParentView = 'home' | 'profile' | 'children' | 'reports' | 'homework' | 'billing' | 'future';
export type ChildView = 'home' | 'learn' | 'assessments' | 'practice-math' | 'practice-ela' | 'practice-writing' | 'homework';
export type View = ParentView | ChildView | 'onboarding' | 'admin';
export type Subject = 'Math' | 'ELA' | 'Writing';

export type StudentProfile = {
  id?: number | string;
  name: string;
  grade: number;
  subjects: Subject[];
  math_level: string;
  ela_level: string;
  writing_level: string;
  confidence: string;
  learning_goals: string;
  difficulty_level: string;
  focus_notes: string;
  parent_notes: string;
  created_at?: string;
};

export type ChatMessage = { role: 'student' | 'msalisia'; content: string; provider?: string; subject?: string };
export type TopicSource = 'manual' | 'default' | 'assessment';

export type TutorStepRecord = {
  step_id?: string;
  label?: string;
  description?: string;
  expression?: string;
  expected_answer?: string;
  result?: string;
  updated_expression?: string;
  status?: string;
  attempts?: number;
  explanation?: string;
};

export type TutorHelperBranch = {
  branch_id?: string;
  branch_type?: string;
  question?: string;
  linked_step_id?: string;
  return_step_id?: string;
  status?: string;
};

export type TutorQueuedQuestion = {
  question_id?: string;
  question?: string;
  subject?: string;
  source?: string;
  status?: string;
};

export type TutoringState = {
  problem_id?: string;
  main_problem?: string;
  active_problem: string;
  current_subject?: string;
  full_problem?: string;
  ordered_steps?: TutorStepRecord[];
  current_step_index?: number;
  current_step_id?: string;
  completed_steps?: string[];
  current_expression?: string;
  remaining_steps?: string[];
  completed_step_results?: string[];
  step_results?: Record<string, string>;
  attempts_per_step?: Record<string, number>;
  current_step: string;
  current_question?: string;
  expected_answer?: string;
  student_answer?: string;
  correctness_status?: string;
  skill?: string;
  step_number?: number;
  attempt_count: number;
  hint_given?: boolean;
  answer_revealed: boolean;
  next_similar_question?: string;
  helper_branch?: TutorHelperBranch;
  queued_followup_questions?: TutorQueuedQuestion[];
  pending_input_kind?: string;
  pending_new_problem?: string;
  paused_main_problem?: string;
  paused_current_step?: string;
  paused_current_question?: string;
  paused_expected_answer?: string;
  paused_completed_steps?: string[];
  return_step_index?: number;
  return_step_id?: string;
  final_answer?: string;
  problem_status?: string;
  mode: string;
  status: string;
  memory_note: string;
};

export type AssessmentResult = {
  subject: Subject;
  enrolled_grade: number;
  assessment_version?: number | null;
  assessment_question_ids?: string[];
  question_results?: AssessmentQuestionResult[];
  correct_count?: number;
  total_questions?: number;
  estimated_level: string;
  score_label: string;
  strengths: string[];
  learning_gaps: string[];
  recommended_progression: string[];
  recommended_next_topics?: string[];
  parent_summary: string;
};

export type AssessmentQuestionResult = {
  question_id: string;
  position: number;
  skill: string;
  question: string;
  student_answer: string;
  expected_answer: string;
  status: string;
  validation_type: string;
  confidence: string;
  feedback_note: string;
  child_feedback: string;
  next_topic_if_incorrect: string;
};

export type AssessmentQuestionPrompt = {
  id: string;
  prompt: string;
};

export type AssessmentSelection = {
  subject: Subject;
  grade: number;
  assessment_version: number;
  question_ids: string[];
  questions: AssessmentQuestionPrompt[];
};

export type ChildAssessmentResult = {
  subject: Subject;
  child_message: string;
  assessment_version?: number | null;
  assessment_question_ids?: string[];
  question_results?: AssessmentQuestionResult[];
  correct_count?: number;
  total_questions?: number;
  estimated_level: string;
  score_label: string;
  strengths: string[];
  learning_gaps: string[];
  recommended_progression: string[];
  recommended_next_topics?: string[];
  parent_summary: string;
  celebration_title?: string;
  celebration_message?: string;
  performance_label?: string;
  score_summary?: string;
  strengths_for_child?: string[];
  practice_next?: string;
  next_step_message?: string;
  badge_label?: string;
  encouragement?: string;
};

export type StoredAssessmentResult = {
  id?: number | string;
  student_name?: string;
  subject: string;
  estimated_level: string;
  learning_gaps?: string;
  recommended_progression?: string;
  parent_summary?: string;
  created_at?: string;
};

export type LLMEvent = {
  id?: number | string;
  provider: string;
  model: string;
  purpose: string;
  fallback_used: number | boolean;
  created_at?: string;
};

export type AdminOverview = {
  totals: {
    users: number;
    admins: number;
    parents: number;
    students: number;
    active_subscriptions: number;
    past_due_subscriptions: number;
  };
  students: StudentProfile[];
  assessments: StoredAssessmentResult[];
  llm_events: LLMEvent[];
  audit_logs: AdminAuditLog[];
};

export type AdminUser = {
  id: string;
  full_name: string;
  email: string;
  role: 'parent' | 'student' | 'admin' | 'super_admin';
  status: 'active' | 'suspended' | 'inactive';
  admin_permissions: string[];
  admin_2fa_enabled: boolean;
  created_at?: string;
  updated_at?: string;
};

export type AdminAuditLog = {
  id?: string;
  admin_user_id?: string;
  action: string;
  target_type: string;
  target_id?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
};

export type AdminSubscription = {
  id: string;
  child_id: string;
  parent_id: string;
  child_name?: string;
  grade_level?: string;
  access_status: 'trial' | 'active' | 'inactive' | 'past_due';
  plan_name: string;
  trial_ends_at?: string | null;
  current_period_ends_at?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type AdminSetting = {
  key: string;
  value: Record<string, unknown>;
  updated_by?: string | null;
  updated_at?: string;
};

export type AdminLearningActivity = {
  child_id: string;
  student_name: string;
  grade_level: string;
  status: 'active' | 'inactive' | 'pending_consent' | string;
  subject: string;
  latest_activity_at?: string | null;
  latest_activity_type: string;
  latest_level?: string | null;
  assessment_count: number;
};

export type OwnerFinancialSummary = {
  currency: string;
  total_revenue_cents_estimate: number;
  current_month_revenue_cents_estimate: number;
  mrr_cents_estimate: number;
  arr_cents_estimate: number;
  active_subscriptions_count: number;
  paused_unpaid_subscriptions_count: number;
  canceled_subscriptions_count: number;
  active_trials_count: number;
  expired_trials_count: number;
  failed_payments_count: number;
  text_plan_count: number;
  voice_plan_count: number;
  monthly_plan_count: number;
  annual_plan_count: number;
  family_discount_usage_count: number;
  coupon_redemption_count: number;
  referral_reward_count: number;
  generated_at?: string;
  notes?: string[];
};

export type OwnerFinancialSubscription = {
  id?: string;
  parent_name?: string | null;
  parent_email?: string | null;
  child_name?: string | null;
  plan_type?: string | null;
  billing_interval?: string | null;
  status?: string | null;
  current_period_ends_at?: string | null;
  amount_cents_estimate?: number;
  amount_display?: string | null;
  discount_status?: string | null;
  family_discount_status?: string | null;
  payment_failure_status?: string | null;
};

export type OwnerFinancialFailedPayment = {
  id?: string;
  parent_email?: string | null;
  child_name?: string | null;
  plan_type?: string | null;
  billing_interval?: string | null;
  amount_cents?: number;
  currency?: string;
  failure_date?: string | null;
  billing_status?: string | null;
  access_status?: string | null;
  grace_period_ends_at?: string | null;
  latest_event_type?: string | null;
};

export type OwnerFinancialDiscount = Record<string, unknown>;
export type OwnerFinancialReferral = Record<string, unknown>;
export type OwnerFinancialEvent = Record<string, unknown>;
