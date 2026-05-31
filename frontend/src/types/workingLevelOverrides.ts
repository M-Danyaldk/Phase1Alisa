import { Subject } from '../types';

export type WorkingLevelOverrideItem = {
  subject: Subject;
  enrolled_grade: string;
  assessed_level?: string | null;
  effective_working_level: string;
  override_level?: string | null;
  override_active: boolean;
  status?: string | null;
  display_text: string;
  updated_at?: string | null;
};

export type WorkingLevelOverridesResponse = {
  child_id: string;
  child_name: string;
  enrolled_grade: string;
  subjects: WorkingLevelOverrideItem[];
};
