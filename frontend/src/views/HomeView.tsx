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
    <SectionHeader title={`Hi, ${firstName(student.name)}!`} desc="What would you like to work on today?" />
    {notice && <p className="success-note dashboard-notice">{notice}</p>}

    <section className="student-home-actions" aria-label="Choose what to do next">
      <StudentHomeAction
        icon={<MessageCircle />}
        title="Learn with Ms. Alisia"
        text="Ask me anything - I'm here to help!"
        view="learn"
        setView={setView}
        featured
      />
      <StudentHomeAction
        icon={<ClipboardCheck />}
        title="Quick Check-In"
        text="Let's see what you know today!"
        view="assessments"
        setView={setView}
      />
      <StudentHomeAction
        icon={<BookOpen />}
        title="Practice Math"
        text="Let's tackle it together!"
        view="practice-math"
        setView={setView}
      />
      <StudentHomeAction
        icon={<BookOpen />}
        title="Practice Reading"
        text="Read, think, and share what you noticed!"
        view="practice-ela"
        setView={setView}
      />
      <StudentHomeAction
        icon={<PenTool />}
        title="Practice Writing"
        text="Let's write something great!"
        view="practice-writing"
        setView={setView}
      />
      <StudentHomeAction
        icon={<ImageUp />}
        title="Homework Help"
        text="Stuck on something? Upload it and I'll help!"
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
