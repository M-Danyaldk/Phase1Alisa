import { classNames } from '../lib/classNames';
import { MarkdownText } from './MarkdownText';
import { ChatMessage, TutoringState } from '../types';

type Props = {
  messages: ChatMessage[];
  input: string;
  loading: boolean;
  historyLoading: boolean;
  tutoringState: TutoringState;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onQuickAction: (prompt: string) => void;
};

export function ChatWorkspace({ messages, input, loading, historyLoading, tutoringState, onInputChange, onSend, onQuickAction }: Props) {
  const skill = tutoringState.skill || 'Practice';
  const step = tutoringState.step_number && tutoringState.step_number > 0 ? `Step ${tutoringState.step_number}` : 'Getting started';

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
    </div>
    <div className="chat-window">
      {historyLoading && <div className="chat-bubble assistant"><p>Loading this conversation...</p></div>}
      {!historyLoading && messages.length === 0 && <div className="chat-empty-state">
        <strong>No messages yet</strong>
        <p>Start with a question or choose an older chat from the sidebar.</p>
      </div>}
      {messages.map((message, index) => <div key={index} className={classNames('chat-bubble', message.role === 'student' ? 'student' : 'assistant')}>
        <MarkdownText text={message.content} />
      </div>)}
      {loading && <div className="chat-bubble assistant"><p>MsAlisia is thinking...</p></div>}
    </div>
    <div className="chat-action-row" aria-label="Learning helper actions">
      <button type="button" onClick={() => onQuickAction('Give me one small hint.')} disabled={loading}>Hint</button>
      <button type="button" onClick={() => onQuickAction('Explain again in simpler words.')} disabled={loading}>Explain again</button>
      <button type="button" onClick={() => onQuickAction('Check my answer: ')} disabled={loading}>Check my answer</button>
      <button type="button" onClick={() => onQuickAction('Give me one short example.')} disabled={loading}>Give me an example</button>
      <button type="button" disabled title="Reporting will be added in a later phase.">Report a Problem</button>
    </div>
    <div className="chat-input">
      <textarea
        value={input}
        onChange={event => onInputChange(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            onSend();
          }
        }}
        aria-label="Message Ms Alisia"
      />
      <button onClick={onSend} className="primary-button" disabled={loading || !input.trim()}>Send</button>
    </div>
  </section>;
}
