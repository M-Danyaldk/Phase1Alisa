import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Circle, Home, Mic, PlayCircle, Square } from 'lucide-react';
import { classNames } from '../lib/classNames';
import { MarkdownText } from './MarkdownText';
import { ProblemReportButton } from './ProblemReportButton';
import { ChatMessage, TutoringState } from '../types';
import { hasActionableTutorTask } from '../lib/quickActions';

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
  onBackHome?: () => void;
  onNewChat?: () => void;
  onQuickAction: (prompt: string) => void;
  onQuickSubmit?: (prompt: string) => void;
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

const CHAT_FALLBACK_MESSAGE = 'No problem - we will use chat instead!';
const VOICE_AUTO_STOP_MS = 2000;
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
  onBackHome,
  onNewChat,
  onQuickAction,
  onQuickSubmit,
  onVoiceNotice,
  onVoiceEnabledChange,
  onVoiceSubmit,
  reportContext,
}: Props) {
  const skill = tutoringState.skill || 'Practice';
  const step = tutoringState.step_number && tutoringState.step_number > 0 ? `Step ${tutoringState.step_number}` : 'Here we go!';
  const inputDisabled = loading || disabled || Boolean(brainBreak?.active);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const autoStopTimerRef = useRef<number | null>(null);
  const autoStoppedRef = useRef(false);
  const voiceUnavailable = inputDisabled || voiceDisabled || voiceProcessing;
  const quickSubmit = onQuickSubmit || onQuickAction;
  const helperDisabled = inputDisabled || !hasActionableTutorTask(tutoringState);
  const checkAnswerDraft = input.trim() ? `Check my answer: ${input.trim()}` : 'My answer is ';

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

  return <section className="chat-card chat-workspace" aria-label="Ms. Alisia chat workspace">
    <div className="chat-topbar">
      <div className="tutor-identity">
        <div className="tutor-avatar">A</div>
        <div>
          <strong>Ms. Alisia</strong>
          <span>You&apos;re chatting with Ms. Alisia, your AI tutor!</span>
        </div>
      </div>
      <div className="lesson-progress" aria-label="Current learning progress">
        <span>{skill}</span>
        <strong>{step}</strong>
      </div>
      {onBackHome && <button type="button" className="secondary-button compact chat-home-button" onClick={() => { onActivity?.(); onBackHome(); }} disabled={historyLoading || loading}>
        <Home aria-hidden="true" />
        Back to Home
      </button>}
      {onNewChat && <button type="button" className="secondary-button compact chat-new-button" onClick={() => { onActivity?.(); onNewChat(); }} disabled={historyLoading || loading}>
        Start Over
      </button>}
    </div>
    <MathStepTracker state={tutoringState} />
    <ClarificationChoicePanel state={tutoringState} disabled={inputDisabled} onChoose={onQuickSubmit || onQuickAction} />
    {(brainBreakWarning || disabledMessage) && !brainBreak?.active && <div className="session-banner" role="status">
      <strong>{brainBreakWarning ? 'Brain Break reminder' : disabled ? 'Learning paused' : 'Learning connection'}</strong>
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
      {!historyLoading && !loading && messages.length === 0 && <div className="chat-empty-state">
        <strong>No messages yet</strong>
        <p>Start with a question, or choose Start Over when you want a fresh activity.</p>
      </div>}
      {messages.map((message, index) => <div key={index} className={classNames('chat-bubble', message.role === 'student' ? 'student' : 'assistant')}>
        <MarkdownText text={message.content} subject={message.subject} />
      </div>)}
      {loading && <div className="chat-bubble assistant"><p>Ms. Alisia is thinking...</p></div>}
    </div>
    <div className="chat-action-row" aria-label="Learning helper actions">
      <button type="button" onClick={() => { onActivity?.(); quickSubmit('Give me one small hint.'); }} disabled={helperDisabled}>Hint</button>
      <button type="button" onClick={() => { onActivity?.(); quickSubmit('Explain again in simpler words.'); }} disabled={helperDisabled}>Explain again</button>
      <button type="button" onClick={() => { onActivity?.(); quickSubmit(checkAnswerDraft); }} disabled={helperDisabled || !input.trim()}>Check my answer</button>
      <button type="button" onClick={() => { onActivity?.(); quickSubmit('Give me one short example.'); }} disabled={helperDisabled}>Give me an example</button>
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
        aria-label="Message Ms. Alisia"
      />
      <button onClick={() => { onActivity?.(); onSend(); }} className="primary-button" disabled={inputDisabled || !input.trim()}>Send</button>
    </div>
  </section>;
}

function ClarificationChoicePanel({
  state,
  disabled,
  onChoose,
}: {
  state: TutoringState;
  disabled: boolean;
  onChoose: (prompt: string) => void;
}) {
  if (state.mode !== 'clarify_new_problem' || !state.pending_new_problem) return null;
  return <section className="clarify-choice-panel" aria-label="Choose how to continue">
    <div>
      <span>Choose next</span>
      <strong>{displayMath(state.pending_new_problem)}</strong>
    </div>
    <div className="clarify-choice-actions">
      <button type="button" onClick={() => onChoose('part of this problem')} disabled={disabled}>Continue current problem</button>
      <button type="button" onClick={() => onChoose('new problem')} disabled={disabled}>Solve new problem first</button>
    </div>
  </section>;
}

function MathStepTracker({ state }: { state: TutoringState }) {
  const steps = state.ordered_steps || [];
  const hasMathPlan = Boolean((state.current_subject === 'Math' || steps.length) && steps.length && state.main_problem);
  if (!hasMathPlan) return null;

  const currentStepId = state.current_step_id || steps[state.current_step_index || 0]?.step_id || '';
  const currentStep = steps.find(item => item.step_id === currentStepId) || steps[state.current_step_index || 0];
  const completedCount = steps.filter(item => item.status === 'complete' || item.result).length;
  const totalCount = steps.length;
  const isFinished = state.problem_status === 'finished';
  const currentLabel = isFinished ? 'Complete' : currentStep?.label || `Step ${Math.max(1, (state.current_step_index || 0) + 1)}`;
  const currentText = isFinished
    ? state.final_answer || state.current_expression || 'Finished'
    : currentStep?.expression || state.current_step || state.current_question || 'Current step';

  return <section className="math-step-tracker" aria-label="Math step tracker">
    <div className="math-tracker-summary">
      <div>
        <span>Main problem</span>
        <strong>{displayMath(state.main_problem || state.active_problem || '')}</strong>
      </div>
      <div>
        <span>{currentLabel}</span>
        <strong>{displayMath(currentText)}</strong>
      </div>
      <div>
        <span>Progress</span>
        <strong>{completedCount}/{totalCount}</strong>
      </div>
    </div>
    <div className="math-step-list" aria-label="Roadmap steps">
      {steps.map((step, index) => {
        const complete = step.status === 'complete' || Boolean(step.result);
        const active = !complete && step.step_id === currentStepId && !isFinished;
        const statusText = complete ? 'Done' : active ? 'Now' : 'Next';
        const stepText = complete || active
          ? step.expression || step.description || ''
          : safeFutureStepText(step.expression || '', step.description || '');
        return <div key={step.step_id || `${step.label}-${index}`} className={classNames('math-step-pill', complete ? 'complete' : '', active ? 'active' : '')}>
          {complete ? <CheckCircle2 aria-hidden="true" /> : active ? <PlayCircle aria-hidden="true" /> : <Circle aria-hidden="true" />}
          <div>
            <span>{step.label || `Step ${index + 1}`} <em>{statusText}</em></span>
            <strong>{displayMath(stepText)}</strong>
          </div>
        </div>;
      })}
    </div>
  </section>;
}

function displayMath(value: string): string {
  return String(value || '').replace(/\*/g, '×');
}

function safeFutureStepText(expression: string, description: string): string {
  const compact = expression.replace(/\s+/g, '');
  const cleanDescription = description.replace(/\s*->.*$/, '').trim();
  if (/\d+\/\d+\+\d+\/\d+/.test(compact)) return 'Add the fraction results';
  if (/\d+\/\d+\+\d+/.test(compact) || /\d+\+\d+\/\d+/.test(compact)) return 'Add the final results';
  if (compact.includes('+')) return 'Add the next results';
  if (compact.includes('-')) return 'Finish the subtraction step';
  if (compact.includes('*')) return cleanDescription || 'Multiply the next part';
  if (compact.includes('/')) return cleanDescription || 'Divide the next part';
  return cleanDescription || 'Next step';
}

function formatRemaining(seconds: number): string {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `${minutes} minute${minutes === 1 ? '' : 's'}`;
}
