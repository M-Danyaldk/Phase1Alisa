import { useEffect, useRef, useState } from 'react';
import { Mic, Square } from 'lucide-react';
import { classNames } from '../lib/classNames';
import { MarkdownText } from './MarkdownText';
import { ProblemReportButton } from './ProblemReportButton';
import { ChatMessage, TutoringState } from '../types';

type Props = {
  messages: ChatMessage[];
  input: string;
  loading: boolean;
  historyLoading: boolean;
  tutoringState: TutoringState;
  disabled?: boolean;
  disabledMessage?: string;
  inactivityNudge?: { message: string; onBack: () => void } | null;
  brainBreak?: { active: boolean; message: string; secondsUntilResume: number } | null;
  brainBreakWarning?: string;
  voiceAllowed?: boolean;
  voiceDisabled?: boolean;
  voiceProcessing?: boolean;
  voiceNotice?: string;
  onActivity?: () => void;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onNewChat?: () => void;
  onQuickAction: (prompt: string) => void;
  onVoiceNotice?: (message: string) => void;
  onVoiceEnabledChange?: (enabled: boolean) => void;
  onVoiceSubmit?: (audio: Blob) => Promise<void>;
  reportContext?: {
    accessToken: string;
    childId: string;
    subject?: 'Math' | 'ELA' | 'Writing';
    studentSession?: boolean;
    sessionId?: string | null;
    threadId?: string | null;
    messageContext?: string | null;
  };
};

const CHAT_FALLBACK_MESSAGE = 'No problem — we will use chat instead!';
const VOICE_AUTO_STOP_MS = 5000;
const VOICE_AUTO_STOP_MESSAGE = 'I stopped recording so we can keep things moving. If you are still there, tap Record and tell me one thing you want help with.';

export function ChatWorkspace({
  messages,
  input,
  loading,
  historyLoading,
  tutoringState,
  disabled = false,
  disabledMessage = '',
  inactivityNudge = null,
  brainBreak = null,
  brainBreakWarning = '',
  voiceAllowed = false,
  voiceDisabled = false,
  voiceProcessing = false,
  voiceNotice = '',
  onActivity,
  onInputChange,
  onSend,
  onNewChat,
  onQuickAction,
  onVoiceNotice,
  onVoiceEnabledChange,
  onVoiceSubmit,
  reportContext,
}: Props) {
  const skill = tutoringState.skill || 'Practice';
  const step = tutoringState.step_number && tutoringState.step_number > 0 ? `Step ${tutoringState.step_number}` : 'Getting started';
  const inputDisabled = loading || disabled || Boolean(brainBreak?.active);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const autoStopTimerRef = useRef<number | null>(null);
  const autoStoppedRef = useRef(false);
  const voiceUnavailable = inputDisabled || voiceDisabled || voiceProcessing;

  useEffect(() => {
    if (!voiceAllowed && voiceEnabled) {
      setVoiceEnabled(false);
      onVoiceEnabledChange?.(false);
    }
  }, [onVoiceEnabledChange, voiceAllowed, voiceEnabled]);

  function supportedMimeType(): string | undefined {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    return candidates.find(type => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(type));
  }

  function stopTracks() {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
  }

  function clearAutoStopTimer() {
    if (autoStopTimerRef.current !== null) {
      window.clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
  }

  useEffect(() => () => {
    clearAutoStopTimer();
    stopTracks();
  }, []);

  async function startRecording() {
    if (!onVoiceSubmit) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      onVoiceNotice?.(CHAT_FALLBACK_MESSAGE);
      return;
    }
    if (voiceUnavailable) return;
    try {
      onActivity?.();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = supportedMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      streamRef.current = stream;
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = event => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        clearAutoStopTimer();
        const stoppedAutomatically = autoStoppedRef.current;
        autoStoppedRef.current = false;
        const type = recorder.mimeType || mimeType || 'audio/webm';
        const audio = new Blob(chunksRef.current, { type });
        chunksRef.current = [];
        stopTracks();
        setRecording(false);
        if (audio.size > 0) {
          onVoiceSubmit(audio)
            .catch(() => onVoiceNotice?.(CHAT_FALLBACK_MESSAGE))
            .finally(() => {
              if (stoppedAutomatically) onVoiceNotice?.(VOICE_AUTO_STOP_MESSAGE);
            });
        } else if (stoppedAutomatically) {
          onVoiceNotice?.(VOICE_AUTO_STOP_MESSAGE);
        }
      };
      recorder.start();
      setRecording(true);
      onVoiceNotice?.('Listening...');
      autoStopTimerRef.current = window.setTimeout(() => {
        const activeRecorder = recorderRef.current;
        if (activeRecorder && activeRecorder.state === 'recording') {
          autoStoppedRef.current = true;
          onVoiceNotice?.(VOICE_AUTO_STOP_MESSAGE);
          activeRecorder.stop();
        }
      }, VOICE_AUTO_STOP_MS);
    } catch {
      clearAutoStopTimer();
      stopTracks();
      setRecording(false);
      onVoiceNotice?.(CHAT_FALLBACK_MESSAGE);
    }
  }

  function stopRecording() {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      clearAutoStopTimer();
      autoStoppedRef.current = false;
      recorder.stop();
      onVoiceNotice?.('Processing your question...');
      return;
    }
    clearAutoStopTimer();
    autoStoppedRef.current = false;
    stopTracks();
    setRecording(false);
  }

  return <section className="chat-card chat-workspace" aria-label="Ms Alisia chat workspace">
    <div className="chat-topbar">
      <div className="tutor-identity">
        <div className="tutor-avatar">A</div>
        <div>
          <strong>Ms Alisia</strong>
          <span>You are chatting with an AI, not a human tutor.</span>
        </div>
      </div>
      <div className="lesson-progress" aria-label="Current learning progress">
        <span>{skill}</span>
        <strong>{step}</strong>
      </div>
      {onNewChat && <button type="button" className="secondary-button compact chat-new-button" onClick={() => { onActivity?.(); onNewChat(); }} disabled={historyLoading || loading}>
        New Chat
      </button>}
    </div>
    {(brainBreakWarning || disabledMessage) && !brainBreak?.active && <div className="session-banner" role="status">
      <strong>{brainBreakWarning ? 'Brain Break reminder' : 'Learning paused'}</strong>
      <span>{brainBreakWarning || disabledMessage}</span>
    </div>}
    {inactivityNudge && !brainBreak?.active && <div className="session-nudge" role="dialog" aria-live="polite" aria-label="Inactivity reminder">
      <div>
        <strong>Still learning?</strong>
        <p>{inactivityNudge.message}</p>
      </div>
      <button type="button" className="primary-button" onClick={inactivityNudge.onBack}>I'm back!</button>
    </div>}
    {brainBreak?.active && <div className="brain-break-lockout" role="status" aria-live="polite">
      <strong>Brain Break time</strong>
      <p>{brainBreak.message}</p>
      {brainBreak.secondsUntilResume > 0 && <span>{formatRemaining(brainBreak.secondsUntilResume)} remaining</span>}
    </div>}
    <div className="chat-window">
      {historyLoading && <div className="chat-bubble assistant"><p>Loading this conversation...</p></div>}
      {!historyLoading && messages.length === 0 && <div className="chat-empty-state">
        <strong>No messages yet</strong>
        <p>Start with a question, or choose New Chat when you want a fresh activity.</p>
      </div>}
      {messages.map((message, index) => <div key={index} className={classNames('chat-bubble', message.role === 'student' ? 'student' : 'assistant')}>
        <MarkdownText text={message.content} />
      </div>)}
      {loading && <div className="chat-bubble assistant"><p>MsAlisia is thinking...</p></div>}
    </div>
    <div className="chat-action-row" aria-label="Learning helper actions">
      <button type="button" onClick={() => { onActivity?.(); onQuickAction('Give me one small hint.'); }} disabled={inputDisabled}>Hint</button>
      <button type="button" onClick={() => { onActivity?.(); onQuickAction('Explain again in simpler words.'); }} disabled={inputDisabled}>Explain again</button>
      <button type="button" onClick={() => { onActivity?.(); onQuickAction('Check my answer: '); }} disabled={inputDisabled}>Check my answer</button>
      <button type="button" onClick={() => { onActivity?.(); onQuickAction('Give me one short example.'); }} disabled={inputDisabled}>Give me an example</button>
      {reportContext && <ProblemReportButton
        accessToken={reportContext.accessToken}
        childId={reportContext.childId}
        source="learning"
        subject={reportContext.subject}
        studentSession={reportContext.studentSession}
        sessionId={reportContext.sessionId}
        threadId={reportContext.threadId}
        messageContext={reportContext.messageContext}
      />}
    </div>
    {voiceAllowed && <div className="voice-panel" aria-label="Voice learning controls">
      <label className="voice-toggle">
        <input
          type="checkbox"
          checked={voiceEnabled}
          onChange={event => {
            const enabled = event.target.checked;
            setVoiceEnabled(enabled);
            onVoiceEnabledChange?.(enabled);
            if (!enabled && recording) stopRecording();
            if (enabled) onVoiceNotice?.('');
          }}
          disabled={inputDisabled || voiceDisabled}
        />
        <span>Voice</span>
      </label>
      {voiceEnabled && <div className="voice-controls">
        <p>Ms. Alisia needs your microphone to hear your question. You can always use chat instead.</p>
        <button
          type="button"
          className={classNames('secondary-button compact', recording ? 'recording' : '')}
          onClick={recording ? stopRecording : startRecording}
          disabled={voiceUnavailable && !recording}
        >
          {recording ? <Square /> : <Mic />}
          {recording ? 'Stop' : voiceProcessing ? 'Processing...' : 'Record'}
        </button>
        {voiceUnavailable && !recording && <span className="muted-note">Voice is paused right now. Chat is still available.</span>}
        {voiceNotice && <span className="muted-note">{voiceNotice}</span>}
      </div>}
    </div>}
    <div className="chat-input">
      <textarea
        value={input}
        onChange={event => {
          onActivity?.();
          onInputChange(event.target.value);
        }}
        onKeyDown={event => {
          onActivity?.();
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (!inputDisabled) onSend();
          }
        }}
        disabled={inputDisabled}
        aria-label="Message Ms Alisia"
      />
      <button onClick={() => { onActivity?.(); onSend(); }} className="primary-button" disabled={inputDisabled || !input.trim()}>Send</button>
    </div>
  </section>;
}

function formatRemaining(seconds: number): string {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `${minutes} minute${minutes === 1 ? '' : 's'}`;
}
