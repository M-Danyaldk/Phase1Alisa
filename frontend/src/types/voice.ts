import { Subject, TopicSource, TutoringState } from '../types';

export type VoiceMessageResponse = {
  transcript: string;
  assistant_text: string;
  assistant_audio_base64?: string | null;
  audio_mime_type?: string | null;
  thread_id?: string | null;
  chat_message_id?: string | null;
  voice_session_id?: string | null;
  fallback_to_chat: boolean;
  error_message?: string | null;
  provider: string;
  model: string;
  tts_model?: string | null;
  tutoring_state: TutoringState;
  history_saved: boolean;
  history_error?: string | null;
  resolved_topic?: string | null;
  topic_source?: TopicSource | null;
  assessed_level?: string | null;
  resolved_subject?: Subject | null;
  subject_changed?: boolean;
  timings: Record<string, number>;
  metadata?: Record<string, unknown>;
};

export type VoiceNudgeResponse = {
  assistant_audio_base64?: string | null;
  audio_mime_type?: string | null;
  fallback_to_chat: boolean;
  error_message?: string | null;
  tts_model?: string | null;
  timings: Record<string, number>;
};
