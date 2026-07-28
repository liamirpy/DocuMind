export type User = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
};

export type AuthResponse = {
  message: string;
  accessToken: string;
  user: User;
};

export type RegisterInput = {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
};

export type LoginInput = {
  email: string;
  password: string;
};

export type Folder = {
  id: string;
  name: string;
  created_at: string;
  updated_at?: string;
  document_count?: number;
};

export type DocumentStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "ready"
  | "processed"
  | "failed"
  | "deleted"
  | string;

export type Document = {
  id: string;
  public_id?: string;
  original_filename: string;
  file_type: string;
  mime_type?: string;
  file_size_bytes: number;
  title?: string | null;
  page_count?: number | null;
  status: DocumentStatus;
  error_message?: string | null;
  uploaded_at: string;
  processed_at?: string | null;
};

export type FolderDetail = {
  folder: Folder;
  documents: Document[];
};

export type ChatScope =
  | { type: "all" }
  | { type: "document"; documentId: string; label: string }
  | { type: "folder"; folderId: string; label: string };

export type Conversation = {
  id: string;
  public_id?: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count?: number;
  last_message?: string | null;
};

export type PdfBoundingBox = {
  l: number;
  b: number;
  r: number;
  t: number;
  coord_origin?: "BOTTOMLEFT" | "TOPLEFT" | string;
};

export type RagSource = {
  citationId: string;
  documentId: string;
  documentPublicId?: string;
  title?: string | null;
  filename?: string | null;
  section?: string | null;
  pageStart?: number | null;
  pageEnd?: number | null;
  sourceType?: string | null;
  matchedChunkId?: string | null;
  contextChunkId?: string | null;
  usedParentContext?: boolean;
  matchTypes?: string[];
  bbox?: PdfBoundingBox | "not available" | null;
  retrievalScore?: number | null;
};

export type ConversationMessage = {
  id: string;
  public_id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  model?: string | null;
  token_count?: number | null;
  created_at?: string;
  sources?: RagSource[];
};

export type ConversationDetail = {
  conversation: Conversation;
  messages: ConversationMessage[];
};

export type RagResponse = {
  answer: string;
  conversation?: Conversation;
  messages?: {
    user?: ConversationMessage;
    assistant?: ConversationMessage;
  };
  result?: {
    context?: unknown;
    hits?: unknown[];
    sources?: RagSource[];
    [key: string]: unknown;
  };
};
