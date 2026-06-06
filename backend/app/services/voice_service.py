import base64
import json
import logging
import time
from typing import Any

import httpx
from fastapi import HTTPException, UploadFile

from ..config import get_settings
from ..models import ChatHistoryItem, StudentProfile, TutoringState
from ..prompts import compact_chat_system_prompt
from ..schemas.chat_history import ChatMessageCreateRequest, ChatThreadCreateRequest
from ..schemas.voice import VoiceMessageResponse
from .access_control import child_billing_access_state
from .chat_store import ChatStore
from .learning_memory_service import LearningMemoryService
from .learning_profile_service import LearningProfileService
from .llm.router import LLMRouter
from .session_activity_service import SessionActivityService
from .topic_resolver import TopicResolver
from .tutor_answer_checker import TutorAnswerChecker
from ..tutoring_logic import build_chat_directives, update_tutoring_state_after_reply
from ..utils.multi_step_progress import build_progress_tracker_directives, update_multi_step_progress
from ..utils.tutor_response import format_student_reply, looks_incomplete_response

logger = logging.getLogger(__name__)

VOICE_FALLBACK_MESSAGE = 'No problem — we will use chat instead!'
UNCLEAR_TRANSCRIPT_MESSAGE = 'I could not hear that clearly. Could you try again?'
MAX_AUDIO_BYTES = 12 * 1024 * 1024


class VoiceService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def synthesize_nudge(self, parent_id: str, child: dict, message: str) -> VoiceMessageResponse:
        timings: dict[str, int] = {}
        total_start = time.perf_counter()
        child_id = child['id']
        await self._ensure_voice_allowed(child_id, child.get('name'))
        await SessionActivityService().ensure_can_tutor(parent_id, child_id)
        try:
            audio_bytes = await self._timed(timings, 'tts_ms', self._synthesize(message))
        except Exception as exc:
            logger.warning('OpenAI TTS nudge failed for child %s: %s', child_id, exc)
            timings['total_ms'] = self._elapsed_ms(total_start)
            return VoiceMessageResponse(
                assistant_text=message,
                fallback_to_chat=True,
                error_message=VOICE_FALLBACK_MESSAGE,
                provider='openai',
                model=self.settings.openai_tts_model or 'gpt-4o-mini-tts',
                timings=timings,
                metadata={'voice_mode': True, 'nudge': True},
            )
        timings['total_ms'] = self._elapsed_ms(total_start)
        return VoiceMessageResponse(
            assistant_text=message,
            assistant_audio_base64=base64.b64encode(audio_bytes).decode('ascii'),
            audio_mime_type='audio/mpeg',
            fallback_to_chat=False,
            provider='openai',
            model=self.settings.openai_tts_model or 'gpt-4o-mini-tts',
            tts_model=self.settings.openai_tts_model,
            timings=timings,
            metadata={'voice_mode': True, 'nudge': True},
        )

    async def handle_message(
        self,
        parent_id: str,
        child: dict,
        audio: UploadFile,
        student: StudentProfile,
        subject: str,
        topic: str = 'general practice',
        topic_source: str = 'manual',
        history: list[ChatHistoryItem] | None = None,
        tutoring_state: TutoringState | None = None,
        thread_id: str | None = None,
    ) -> VoiceMessageResponse:
        timings: dict[str, int] = {}
        total_start = time.perf_counter()
        child_id = child['id']

        await self._ensure_voice_allowed(child_id, child.get('name'))
        await SessionActivityService().ensure_can_tutor(parent_id, child_id)

        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=422, detail='Audio is required.')
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail='Voice message is too long. Please try a shorter recording.')

        transcript = await self._timed(timings, 'stt_ms', self._transcribe(audio_bytes, audio.content_type or 'application/octet-stream'))
        if not transcript:
            timings['total_ms'] = self._elapsed_ms(total_start)
            return VoiceMessageResponse(
                assistant_text=UNCLEAR_TRANSCRIPT_MESSAGE,
                fallback_to_chat=True,
                error_message=UNCLEAR_TRANSCRIPT_MESSAGE,
                provider='deepgram',
                model='stt',
                timings=timings,
            )

        await SessionActivityService().record_activity(
            parent_id,
            child_id,
            subject=subject,
            topic=topic,
            event_type='message_sent',
        )

        chat_result = await self._timed(
            timings,
            'llm_ms',
            self._generate_tutoring_response(
                parent_id=parent_id,
                child=child,
                student=student,
                subject=subject,
                topic=topic,
                topic_source=topic_source,
                transcript=transcript,
                history=history or [],
                tutoring_state=tutoring_state or TutoringState(),
                thread_id=thread_id,
            ),
        )

        audio_base64 = None
        audio_mime_type = None
        tts_error = None
        try:
            tts_bytes = await self._timed(timings, 'tts_ms', self._synthesize(chat_result['assistant_text']))
            audio_base64 = base64.b64encode(tts_bytes).decode('ascii')
            audio_mime_type = 'audio/mpeg'
        except Exception as exc:
            logger.warning('OpenAI TTS failed for child %s: %s', child_id, exc)
            tts_error = VOICE_FALLBACK_MESSAGE

        await SessionActivityService().exchange_complete(
            parent_id,
            child_id,
            subject=subject,
            topic=chat_result.get('resolved_topic') or topic,
        )

        timings['total_ms'] = self._elapsed_ms(total_start)
        return VoiceMessageResponse(
            transcript=transcript,
            assistant_text=chat_result['assistant_text'],
            assistant_audio_base64=audio_base64,
            audio_mime_type=audio_mime_type,
            thread_id=chat_result.get('thread_id'),
            chat_message_id=chat_result.get('assistant_message_id'),
            voice_session_id=chat_result.get('thread_id'),
            fallback_to_chat=bool(tts_error),
            error_message=tts_error,
            provider=chat_result.get('provider') or 'unknown',
            model=chat_result.get('model') or 'unknown',
            tts_model=self.settings.openai_tts_model if audio_base64 else None,
            tutoring_state=chat_result['tutoring_state'],
            history_saved=chat_result.get('history_saved', False),
            history_error=chat_result.get('history_error'),
            resolved_topic=chat_result.get('resolved_topic'),
            topic_source=chat_result.get('topic_source'),
            assessed_level=chat_result.get('assessed_level'),
            timings=timings,
            metadata={'voice_mode': True, 'raw_audio_stored': False},
        )

    async def _ensure_voice_allowed(self, child_id: str, child_name: str | None) -> None:
        billing_state = await child_billing_access_state(child_id, child_name=child_name)
        if not billing_state.get('access_allowed'):
            raise HTTPException(status_code=403, detail=billing_state.get('child_blocked_message') or VOICE_FALLBACK_MESSAGE)
        if not billing_state.get('voice_allowed'):
            raise HTTPException(status_code=403, detail='Voice learning is available on Chat + Audio plans.')

    async def _transcribe(self, audio_bytes: bytes, content_type: str) -> str:
        if not self.settings.deepgram_api_key:
            raise HTTPException(status_code=503, detail=VOICE_FALLBACK_MESSAGE)
        params = {
            'model': 'nova-2',
            'language': 'en-US',
            'punctuate': 'true',
            'smart_format': 'true',
            'filler_words': 'false',
            'utterances': 'false',
        }
        headers = {
            'Authorization': f'Token {self.settings.deepgram_api_key}',
            'Content-Type': content_type,
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(self.settings.deepgram_api_url, params=params, headers=headers, content=audio_bytes)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning('Deepgram STT failed: %s', exc)
            raise HTTPException(status_code=503, detail=VOICE_FALLBACK_MESSAGE) from exc
        data = response.json()
        transcript = (
            (((data.get('results') or {}).get('channels') or [{}])[0].get('alternatives') or [{}])[0].get('transcript') or ''
        )
        return ' '.join(str(transcript).split()).strip()

    async def _generate_tutoring_response(
        self,
        parent_id: str,
        child: dict,
        student: StudentProfile,
        subject: str,
        topic: str,
        topic_source: str,
        transcript: str,
        history: list[ChatHistoryItem],
        tutoring_state: TutoringState,
        thread_id: str | None,
    ) -> dict:
        child_id = child['id']
        assessment_context = await LearningProfileService().context_for_child_subject(child_id, subject)
        learning_memory_service = LearningMemoryService()
        topic_resolution = TopicResolver().resolve(
            subject=subject,
            topic=topic,
            topic_source=topic_source,
            assessment_context=assessment_context,
        )
        resolved_topic = topic_resolution['topic']
        prior_memory = await learning_memory_service.relevant_for_child_subject(
            child_id,
            subject,
            topic=resolved_topic,
            student_message=transcript,
            working_level=(assessment_context or {}).get('assessed_level'),
        )
        prompt_student = self._student_with_assessed_level(self._student_from_child(student, child), subject, assessment_context)

        chat_store: ChatStore | None = None
        chat_thread_id = thread_id
        history_saved = False
        history_error = None
        assistant_message_id = None
        try:
            chat_store = ChatStore()
            if not chat_thread_id:
                thread = await chat_store.create_thread(parent_id, ChatThreadCreateRequest(
                    child_id=child_id,
                    subject=subject,
                    topic=resolved_topic,
                    title=transcript[:48] or None,
                ))
                chat_thread_id = thread['id']
            if chat_thread_id:
                await chat_store.store_message(parent_id, ChatMessageCreateRequest(
                    thread_id=chat_thread_id,
                    child_id=child_id,
                    role='student',
                    content=transcript,
                    subject=subject,
                    topic=resolved_topic,
                    tutoring_state={**tutoring_state.model_dump(), 'voice_mode': True},
                ))
        except Exception as exc:
            logger.warning('Voice chat history setup failed before LLM response: %s', exc)
            chat_store = None
            history_error = str(exc)

        directives, active_task, current_step, next_state = build_chat_directives(transcript, history, tutoring_state)
        next_state = next_state.model_copy(update={'current_subject': subject})
        next_state = update_multi_step_progress(transcript, next_state)
        answer_check = None
        if next_state.attempt_count > 0 and (next_state.current_question or current_step):
            answer_check = await TutorAnswerChecker().check(
                subject=subject,
                question=next_state.current_question or current_step,
                student_answer=transcript,
                expected_answer=next_state.expected_answer,
            )
            next_state = next_state.model_copy(update={
                'current_subject': subject,
                'student_answer': transcript,
                'correctness_status': answer_check.status,
                'expected_answer': answer_check.expected_answer or next_state.expected_answer,
                'hint_given': answer_check.is_wrong and next_state.attempt_count == 1,
                'answer_revealed': answer_check.is_wrong and next_state.attempt_count >= 2,
            })
            if answer_check.is_correct:
                directives.append('Backend answer check: correct. Praise briefly, then give one small next step or one new same-topic question.')
            elif next_state.attempt_count == 1:
                directives.append('Backend answer check: wrong or unclear on first attempt. Give one helpful hint only. Do not reveal the final answer. Ask the student to try the same question again.')
            else:
                directives.append('Backend answer check: wrong or unclear on second attempt. Give the correct answer, explain it simply, then give one similar new practice question. Do not ask the same question again.')
                if answer_check.expected_answer:
                    directives.append(f'Correct answer to explain: {answer_check.expected_answer}')
            if answer_check.feedback_note:
                directives.append(f'Answer-check note: {answer_check.feedback_note}')

        directives = [
            f'The currently selected subject is {subject}. Stay in this subject unless the student clearly asks to switch to another subject.',
            'This message came from voice input. Reply naturally for spoken audio: warm, calm, and concise.',
            'Lead the spoken activity with one clear next step. Do not ask broad questions when assessment, homework, or current task context is available.',
            'Ask only one question at a time. Do not include multiple open-ended questions in one spoken reply.',
            'Use assessment results when available: start from the assessed working level, recommended topic, or recommended next step before starting unrelated practice.',
            'After the current problem is finished, you may end with one short same-subject practice question or mini-check when helpful. Do not add a new practice question before the current step is settled.',
            'Use compact tutor chat: 5-7 short lines maximum for normal help.',
            'For direct math questions, include the main step, calculation, and **Final answer:**.',
            'Use Markdown bold only for short labels such as **Step 1:** and **Final answer:**.',
            'Do not use * for multiplication. Use x for multiplication and / for division.',
            'Do not end with an unfinished sentence or a heading without content.',
            *build_progress_tracker_directives(next_state),
            *learning_memory_service.memory_directives(prior_memory),
            *directives,
        ]
        system = compact_chat_system_prompt(prompt_student, subject, resolved_topic, directives, active_task, assessment_context)
        recent_history = '\n'.join([f'{item.role}: {item.content}' for item in history[-4:]])
        state_summary = (
            f"Mode: {next_state.mode}; "
            f"Attempt count: {next_state.attempt_count}; "
            f"Correctness: {next_state.correctness_status or 'not checked'}; "
            f"Memory: {next_state.memory_note or 'none'}"
        )
        user = f"Recent chat:\n{recent_history}\n\nTutoring state:\n{state_summary}\n\nActive task to keep helping with: {active_task or transcript}\n\nCurrent step to focus on first: {current_step or 'No locked step yet.'}\n\nStudent says: {transcript}\n\nRespond as Ms Alisia using the required tutoring method."
        result = await LLMRouter().generate(system=system, user=user, purpose='chat')
        formatted_reply = format_student_reply(result.text)
        if looks_incomplete_response(formatted_reply, transcript):
            continuation_user = (
                f'{user}\n\n'
                f'Previous incomplete answer:\n{formatted_reply}\n\n'
                'Finish the answer briefly and include the final answer. Do not restart.'
            )
            continuation = await LLMRouter().generate(system=system, user=continuation_user, purpose='chat')
            result.provider = continuation.provider
            result.model = continuation.model
            result.fallback_used = result.fallback_used or continuation.fallback_used
            formatted_reply = format_student_reply(f'{formatted_reply}\n\n{continuation.text}')
        final_state = update_tutoring_state_after_reply(next_state, transcript, formatted_reply)

        if chat_store and chat_thread_id:
            try:
                message = await chat_store.store_message(parent_id, ChatMessageCreateRequest(
                    thread_id=chat_thread_id,
                    child_id=child_id,
                    role='msalisia',
                    content=formatted_reply,
                    subject=subject,
                    topic=resolved_topic,
                    provider=result.provider,
                    model=result.model,
                    tutoring_state={**final_state.model_dump(), 'voice_mode': True},
                ))
                assistant_message_id = message.get('id')
                history_saved = True
            except Exception as exc:
                logger.warning('Voice chat history save failed after LLM response: %s', exc)
                history_error = str(exc)

        await learning_memory_service.record_exchange_summary(
            parent_id=parent_id,
            child_id=child_id,
            subject=subject,
            topic=resolved_topic,
            grade_level=child.get('grade_level'),
            working_level=(assessment_context or {}).get('assessed_level'),
            student_message=transcript,
            assistant_text=formatted_reply,
            tutoring_state=final_state,
            thread_id=chat_thread_id,
            source='voice_session',
            metadata={
                'provider': result.provider,
                'model': result.model,
                'topic_source': topic_resolution['source'],
                'assessed_level': topic_resolution.get('assessed_level'),
                'voice_mode': True,
            },
        )

        return {
            'assistant_text': formatted_reply,
            'provider': result.provider,
            'model': result.model,
            'tutoring_state': final_state,
            'thread_id': chat_thread_id,
            'assistant_message_id': assistant_message_id,
            'history_saved': history_saved,
            'history_error': history_error,
            'resolved_topic': resolved_topic,
            'topic_source': topic_resolution['source'],
            'assessed_level': topic_resolution.get('assessed_level'),
        }

    async def _synthesize(self, text: str) -> bytes:
        if not self.settings.openai_api_key:
            raise HTTPException(status_code=503, detail=VOICE_FALLBACK_MESSAGE)
        payload = {
            'model': self.settings.openai_tts_model or 'gpt-4o-mini-tts',
            'voice': self.settings.openai_tts_voice or 'nova',
            'input': text,
            'response_format': 'mp3',
        }
        headers = {
            'Authorization': f'Bearer {self.settings.openai_api_key}',
            'Content-Type': 'application/json',
        }
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(self.settings.openai_tts_api_url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning('OpenAI TTS request failed: %s', exc)
            raise HTTPException(status_code=503, detail=VOICE_FALLBACK_MESSAGE) from exc
        return response.content

    async def _timed(self, timings: dict[str, int], key: str, awaitable):
        start = time.perf_counter()
        try:
            return await awaitable
        finally:
            timings[key] = self._elapsed_ms(start)

    def _elapsed_ms(self, start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    def _student_from_child(self, student: StudentProfile, child: dict) -> StudentProfile:
        return student.model_copy(update={
            'name': child.get('name') or student.name,
            'grade': self._grade_number(child.get('grade_level')) or student.grade,
        })

    def _student_with_assessed_level(self, student: StudentProfile, subject: str, assessment_context: dict | None) -> StudentProfile:
        assessed_level = (assessment_context or {}).get('assessed_level')
        if not assessed_level:
            return student
        updates = {}
        if subject == 'Math':
            updates['math_level'] = assessed_level
        elif subject == 'ELA':
            updates['ela_level'] = assessed_level
        elif subject == 'Writing':
            updates['writing_level'] = assessed_level
        return student.model_copy(update=updates) if updates else student

    def _grade_number(self, value: object) -> int | None:
        text = str(value or '')
        digits = ''.join(character for character in text if character.isdigit())
        if not digits:
            return None
        grade = int(digits)
        return grade if 3 <= grade <= 12 else None


def parse_voice_json(value: str, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
