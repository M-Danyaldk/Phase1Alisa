import { apiPost, apiPostForm } from '../api';
import { ChatMessage, StudentProfile, Subject, TopicSource, TutorSurfaceContext, TutoringState } from '../../types';
import { VoiceMessageResponse, VoiceNudgeResponse } from '../../types/voice';

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

export function sendVoiceMessage({
  accessToken,
  audio,
  student,
  childId,
  subject,
  topic,
  topicSource,
  surfaceContext = 'start_learning',
  history,
  tutoringState,
  threadId,
}: {
  accessToken: string;
  audio: Blob;
  student: StudentProfile;
  childId: string;
  subject: Subject;
  topic: string;
  topicSource: TopicSource;
  surfaceContext?: TutorSurfaceContext;
  history: ChatMessage[];
  tutoringState: TutoringState;
  threadId?: string | null;
}): Promise<VoiceMessageResponse> {
  const payload = new FormData();
  payload.append('audio', audio, `voice-message.${audioExtension(audio.type)}`);
  payload.append('student_json', JSON.stringify(student));
  payload.append('child_id', childId);
  payload.append('subject', subject);
  payload.append('topic', topic);
  payload.append('topic_source', topicSource);
  payload.append('surface_context', surfaceContext);
  payload.append('history_json', JSON.stringify(history));
  payload.append('tutoring_state_json', JSON.stringify(tutoringState));
  if (threadId) payload.append('thread_id', threadId);
  return apiPostForm<VoiceMessageResponse>('/api/voice/message', payload, authHeaders(accessToken));
}

export function sendVoiceNudge(accessToken: string, childId: string, message: string): Promise<VoiceNudgeResponse> {
  return apiPost<VoiceNudgeResponse>('/api/voice/nudge', { child_id: childId, message }, authHeaders(accessToken));
}

function audioExtension(contentType: string): string {
  if (contentType.includes('mp4')) return 'mp4';
  if (contentType.includes('ogg')) return 'ogg';
  if (contentType.includes('wav')) return 'wav';
  return 'webm';
}
