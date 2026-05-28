export type HomeworkUpload = {
  id?: string | null;
  child_id: string;
  parent_id?: string | null;
  uploaded_by_type?: string;
  uploader_type?: string;
  source: string;
  file_name: string;
  mime_type?: string;
  file_type: string;
  file_size_bytes?: number;
  upload_status: string;
  ai_validation_status: string;
  ai_validation_summary?: string | null;
  is_unclear: boolean;
  detected_subject?: string | null;
  suggested_next_step?: string | null;
  provider?: string | null;
  model?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type HomeworkHistoryResponse = {
  child_id: string;
  uploads: HomeworkUpload[];
};
