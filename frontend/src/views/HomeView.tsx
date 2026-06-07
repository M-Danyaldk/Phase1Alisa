import type { ReactNode } from 'react';
import { BookOpen, ClipboardCheck, ImageUp, MessageCircle, PenTool } from 'lucide-react';
import { SectionHeader } from '../components/SectionHeader';
import { ChildView, StudentProfile, View } from '../types';

export function HomeView({
  student,
  accessToken = '',
  childId = '',
  studentSession = false,
  notice = '',
  setView,
}: {
  student: StudentProfile;
  accessToken?: string;
  childId?: string;
  studentSession?: boolean;
  notice?: string;
  setView: (v: View) => void;
}) {
  void accessToken;
  void childId;
  void studentSession;

  return <div className="page-stack student-home-page">
    <SectionHeader title={`Hi, ${firstName(student.name)}!`} desc="Ready to learn today?" />
    {notice && <p className="success-note dashboard-notice">{notice}</p>}

    <section className="student-home-actions" aria-label="Choose what to do next">
      <StudentHomeAction
        icon={<MessageCircle />}
        title="Start Learning"
        text="Ask Ms. Alisia for help."
        view="learn"
        setView={setView}
        featured
      />
      <StudentHomeAction
        icon={<ClipboardCheck />}
        title="Quick Check-In"
        text="Try a short skill check."
        view="assessments"
        setView={setView}
      />
      <StudentHomeAction
        icon={<BookOpen />}
        title="Practice Reading"
        text="Read, think, and answer."
        view="practice-ela"
        setView={setView}
      />
      <StudentHomeAction
        icon={<BookOpen />}
        title="Practice Math"
        text="Work one step at a time."
        view="practice-math"
        setView={setView}
      />
      <StudentHomeAction
        icon={<PenTool />}
        title="Practice Writing"
        text="Plan, write, and improve."
        view="practice-writing"
        setView={setView}
      />
      <StudentHomeAction
        icon={<ImageUp />}
        title="Homework Help"
        text="Upload homework for help."
        view="homework"
        setView={setView}
      />
    </section>
  </div>;
}

function StudentHomeAction({
  icon,
  title,
  text,
  view,
  setView,
  featured = false,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  view: ChildView;
  setView: (v: View) => void;
  featured?: boolean;
}) {
  return <button className={`student-home-action${featured ? ' featured' : ''}`} type="button" onClick={() => setView(view)}>
    <span className="student-home-action-icon">{icon}</span>
    <strong>{title}</strong>
    <small>{text}</small>
  </button>;
}

function firstName(name: string): string {
  const value = name.trim().split(/\s+/)[0] || 'there';
  return value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
}
