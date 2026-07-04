BEGIN;

-- =========================================================
-- Required extensions
-- =========================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- =========================================================
-- Public readable ID sequences
-- =========================================================
CREATE SEQUENCE IF NOT EXISTS user_public_id_seq START 1000000;
CREATE SEQUENCE IF NOT EXISTS document_public_id_seq START 1000000;
CREATE SEQUENCE IF NOT EXISTS processing_job_public_id_seq START 1000000;
CREATE SEQUENCE IF NOT EXISTS document_chunk_public_id_seq START 1000000;
CREATE SEQUENCE IF NOT EXISTS conversation_public_id_seq START 1000000;
CREATE SEQUENCE IF NOT EXISTS message_public_id_seq START 1000000;
CREATE SEQUENCE IF NOT EXISTS message_source_public_id_seq START 1000000;
CREATE SEQUENCE IF NOT EXISTS folder_public_id_seq START 1000000;

-- =========================================================
-- users
-- =========================================================
CREATE TABLE IF NOT EXISTS public.users
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    public_id text NOT NULL UNIQUE
        DEFAULT ('U' || nextval('user_public_id_seq')::text),

    first_name text,
    last_name text,

    email citext NOT NULL UNIQUE,
    password_hash text NOT NULL,

    email_verified_at timestamp with time zone,
    is_active boolean NOT NULL DEFAULT true,

    role text NOT NULL DEFAULT 'user'
        CHECK (role IN ('user', 'admin')),

    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    last_login_at timestamp with time zone
);

-- =========================================================
-- documents
-- Supports: PDF, TXT, JSON, NIfTI (.nii), compressed NIfTI (.nii.gz)
-- =========================================================
CREATE TABLE IF NOT EXISTS public.documents
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    public_id text NOT NULL UNIQUE
        DEFAULT ('D' || nextval('document_public_id_seq')::text),

    user_id uuid NOT NULL,

    original_filename text NOT NULL,

    file_type text NOT NULL
        CHECK (file_type IN ('pdf', 'txt', 'json', 'nii', 'nii.gz')),

    mime_type text,

    -- Store a private storage path/key, not a public URL.
    -- Example:
    -- users/{user_id}/documents/{document_id}/file.pdf
    storage_key text NOT NULL,

    file_size_bytes bigint NOT NULL
        CHECK (file_size_bytes > 0),

    sha256_hash text NOT NULL
        CHECK (sha256_hash ~ '^[a-fA-F0-9]{64}$'),

    title text,

    page_count integer
        CHECK (page_count IS NULL OR page_count > 0),

    status text NOT NULL DEFAULT 'uploaded'
        CHECK (status IN ('uploaded', 'processing', 'ready', 'failed', 'deleted')),

    error_message text,

    uploaded_at timestamp with time zone NOT NULL DEFAULT now(),
    processed_at timestamp with time zone,
    deleted_at timestamp with time zone,

    FOREIGN KEY (user_id)
        REFERENCES public.users(id)
        ON DELETE CASCADE,

    UNIQUE (user_id, sha256_hash),
    UNIQUE (id, user_id)
);

-- =========================================================
-- folders
-- User-created folders for grouping documents
-- =========================================================
CREATE TABLE IF NOT EXISTS public.folders
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    public_id text NOT NULL UNIQUE
        DEFAULT ('F' || nextval('folder_public_id_seq')::text),

    user_id uuid NOT NULL,

    name text NOT NULL,
    description text,

    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    deleted_at timestamp with time zone,

    FOREIGN KEY (user_id)
        REFERENCES public.users(id)
        ON DELETE CASCADE,

    UNIQUE (id, user_id),
    UNIQUE (user_id, name)
);

-- =========================================================
-- folder_documents
-- Connects folders and documents.
-- One folder can contain many documents.
-- One document can be placed in many folders.
-- =========================================================
CREATE TABLE IF NOT EXISTS public.folder_documents
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id uuid NOT NULL,
    folder_id uuid NOT NULL,
    document_id uuid NOT NULL,

    added_at timestamp with time zone NOT NULL DEFAULT now(),
    deleted_at timestamp with time zone,

    FOREIGN KEY (folder_id, user_id)
        REFERENCES public.folders(id, user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (document_id, user_id)
        REFERENCES public.documents(id, user_id)
        ON DELETE CASCADE,

    UNIQUE (folder_id, document_id)
);

-- =========================================================
-- document_processing_jobs
-- =========================================================
CREATE TABLE IF NOT EXISTS public.document_processing_jobs
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    public_id text NOT NULL UNIQUE
        DEFAULT ('J' || nextval('processing_job_public_id_seq')::text),

    document_id uuid NOT NULL,
    user_id uuid NOT NULL,

    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),

    job_type text NOT NULL DEFAULT 'full_processing'
        CHECK (job_type IN (
            'full_processing',
            'extract_text',
            'extract_metadata',
            'process_nifti',
            'chunk',
            'embed',
            'index_elasticsearch'
        )),

    attempt_count integer NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),

    started_at timestamp with time zone,
    finished_at timestamp with time zone,

    error_message text,

    created_at timestamp with time zone NOT NULL DEFAULT now(),

    FOREIGN KEY (document_id, user_id)
        REFERENCES public.documents(id, user_id)
        ON DELETE CASCADE,

    CHECK (
        finished_at IS NULL
        OR started_at IS NULL
        OR finished_at >= started_at
    )
);

-- =========================================================
-- document_chunks
-- =========================================================
CREATE TABLE IF NOT EXISTS public.document_chunks
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    public_id text NOT NULL UNIQUE
        DEFAULT ('CH' || nextval('document_chunk_public_id_seq')::text),

    document_id uuid NOT NULL,
    user_id uuid NOT NULL,

    chunk_index integer NOT NULL
        CHECK (chunk_index >= 0),

    page_start integer
        CHECK (page_start IS NULL OR page_start > 0),

    page_end integer
        CHECK (page_end IS NULL OR page_end > 0),

    token_count integer
        CHECK (token_count IS NULL OR token_count > 0),

    -- ID of the matching document in Elasticsearch
    elasticsearch_document_id text NOT NULL,

    -- Name of the Elasticsearch index
    elasticsearch_index_name text NOT NULL,

    embedding_model text NOT NULL,

    embedding_dimensions integer
        CHECK (embedding_dimensions IS NULL OR embedding_dimensions > 0),

    chunking_strategy text,

    content_hash text
        CHECK (content_hash IS NULL OR content_hash ~ '^[a-fA-F0-9]{64}$'),

    created_at timestamp with time zone NOT NULL DEFAULT now(),

    FOREIGN KEY (document_id, user_id)
        REFERENCES public.documents(id, user_id)
        ON DELETE CASCADE,

    UNIQUE (id, user_id),
    UNIQUE (document_id, chunk_index),
    UNIQUE (elasticsearch_index_name, elasticsearch_document_id),

    CHECK (
        page_start IS NULL
        OR page_end IS NULL
        OR page_end >= page_start
    )
);

-- =========================================================
-- conversations
-- =========================================================
CREATE TABLE IF NOT EXISTS public.conversations
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    public_id text NOT NULL UNIQUE
        DEFAULT ('C' || nextval('conversation_public_id_seq')::text),

    user_id uuid NOT NULL,

    title text,

    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),

    deleted_at timestamp with time zone,

    FOREIGN KEY (user_id)
        REFERENCES public.users(id)
        ON DELETE CASCADE,

    UNIQUE (id, user_id)
);

-- =========================================================
-- messages
-- =========================================================
CREATE TABLE IF NOT EXISTS public.messages
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    public_id text NOT NULL UNIQUE
        DEFAULT ('M' || nextval('message_public_id_seq')::text),

    conversation_id uuid NOT NULL,
    user_id uuid NOT NULL,

    role text NOT NULL
        CHECK (role IN ('user', 'assistant', 'system')),

    content text NOT NULL,

    model text,

    token_count integer
        CHECK (token_count IS NULL OR token_count >= 0),

    created_at timestamp with time zone NOT NULL DEFAULT now(),

    FOREIGN KEY (conversation_id, user_id)
        REFERENCES public.conversations(id, user_id)
        ON DELETE CASCADE,

    UNIQUE (id, user_id)
);

-- =========================================================
-- message_sources
-- Stores RAG citations/sources for assistant messages
-- =========================================================
CREATE TABLE IF NOT EXISTS public.message_sources
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    public_id text NOT NULL UNIQUE
        DEFAULT ('MS' || nextval('message_source_public_id_seq')::text),

    user_id uuid NOT NULL,

    message_id uuid NOT NULL,
    document_id uuid NOT NULL,
    chunk_id uuid NOT NULL,

    rank integer
        CHECK (rank IS NULL OR rank > 0),

    relevance_score double precision
        CHECK (relevance_score IS NULL OR relevance_score >= 0),

    page_start integer
        CHECK (page_start IS NULL OR page_start > 0),

    page_end integer
        CHECK (page_end IS NULL OR page_end > 0),

    created_at timestamp with time zone NOT NULL DEFAULT now(),

    FOREIGN KEY (message_id, user_id)
        REFERENCES public.messages(id, user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (document_id, user_id)
        REFERENCES public.documents(id, user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (chunk_id, user_id)
        REFERENCES public.document_chunks(id, user_id)
        ON DELETE CASCADE,

    UNIQUE (message_id, chunk_id),

    CHECK (
        page_start IS NULL
        OR page_end IS NULL
        OR page_end >= page_start
    )
);

-- =========================================================
-- user_sessions
-- No public_id here because sessions are internal/security-sensitive
-- =========================================================
CREATE TABLE IF NOT EXISTS public.user_sessions
(
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id uuid NOT NULL,

    refresh_token_hash text NOT NULL UNIQUE,

    ip_address inet,
    user_agent text,

    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    last_used_at timestamp with time zone,

    created_at timestamp with time zone NOT NULL DEFAULT now(),

    FOREIGN KEY (user_id)
        REFERENCES public.users(id)
        ON DELETE CASCADE,

    CHECK (
        revoked_at IS NULL
        OR revoked_at >= created_at
    ),

    CHECK (
        expires_at > created_at
    )
);

-- =========================================================
-- updated_at trigger helper
-- =========================================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON public.users;
CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON public.users
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_folders_set_updated_at ON public.folders;
CREATE TRIGGER trg_folders_set_updated_at
BEFORE UPDATE ON public.folders
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_conversations_set_updated_at ON public.conversations;
CREATE TRIGGER trg_conversations_set_updated_at
BEFORE UPDATE ON public.conversations
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- =========================================================
-- indexes
-- =========================================================

-- users
CREATE INDEX IF NOT EXISTS idx_users_email
    ON public.users(email);

CREATE INDEX IF NOT EXISTS idx_users_public_id
    ON public.users(public_id);

CREATE INDEX IF NOT EXISTS idx_users_role
    ON public.users(role);

-- documents
CREATE INDEX IF NOT EXISTS idx_documents_user_id
    ON public.documents(user_id);

CREATE INDEX IF NOT EXISTS idx_documents_user_status
    ON public.documents(user_id, status);

CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at
    ON public.documents(uploaded_at);

CREATE INDEX IF NOT EXISTS idx_documents_deleted_at
    ON public.documents(deleted_at);

CREATE INDEX IF NOT EXISTS idx_documents_public_id
    ON public.documents(public_id);

CREATE INDEX IF NOT EXISTS idx_documents_file_type
    ON public.documents(file_type);

-- folders
CREATE INDEX IF NOT EXISTS idx_folders_user_id
    ON public.folders(user_id);

CREATE INDEX IF NOT EXISTS idx_folders_user_name
    ON public.folders(user_id, name);

CREATE INDEX IF NOT EXISTS idx_folders_deleted_at
    ON public.folders(deleted_at);

CREATE INDEX IF NOT EXISTS idx_folders_public_id
    ON public.folders(public_id);

-- folder_documents
CREATE INDEX IF NOT EXISTS idx_folder_documents_user_id
    ON public.folder_documents(user_id);

CREATE INDEX IF NOT EXISTS idx_folder_documents_folder_id
    ON public.folder_documents(folder_id);

CREATE INDEX IF NOT EXISTS idx_folder_documents_document_id
    ON public.folder_documents(document_id);

CREATE INDEX IF NOT EXISTS idx_folder_documents_active_folder
    ON public.folder_documents(folder_id, document_id)
    WHERE deleted_at IS NULL;

-- document_processing_jobs
CREATE INDEX IF NOT EXISTS idx_document_processing_jobs_document_id
    ON public.document_processing_jobs(document_id);

CREATE INDEX IF NOT EXISTS idx_document_processing_jobs_user_id
    ON public.document_processing_jobs(user_id);

CREATE INDEX IF NOT EXISTS idx_document_processing_jobs_user_status
    ON public.document_processing_jobs(user_id, status);

CREATE INDEX IF NOT EXISTS idx_document_processing_jobs_status
    ON public.document_processing_jobs(status);

CREATE INDEX IF NOT EXISTS idx_document_processing_jobs_created_at
    ON public.document_processing_jobs(created_at);

-- document_chunks
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
    ON public.document_chunks(document_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_user_id
    ON public.document_chunks(user_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_chunk_index
    ON public.document_chunks(document_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_document_chunks_public_id
    ON public.document_chunks(public_id);

-- conversations
CREATE INDEX IF NOT EXISTS idx_conversations_user_id
    ON public.conversations(user_id);

CREATE INDEX IF NOT EXISTS idx_conversations_user_updated_at
    ON public.conversations(user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversations_deleted_at
    ON public.conversations(deleted_at);

CREATE INDEX IF NOT EXISTS idx_conversations_public_id
    ON public.conversations(public_id);

-- messages
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
    ON public.messages(conversation_id);

CREATE INDEX IF NOT EXISTS idx_messages_user_id
    ON public.messages(user_id);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created_at
    ON public.messages(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_messages_public_id
    ON public.messages(public_id);

-- message_sources
CREATE INDEX IF NOT EXISTS idx_message_sources_message_id
    ON public.message_sources(message_id);

CREATE INDEX IF NOT EXISTS idx_message_sources_document_id
    ON public.message_sources(document_id);

CREATE INDEX IF NOT EXISTS idx_message_sources_chunk_id
    ON public.message_sources(chunk_id);

CREATE INDEX IF NOT EXISTS idx_message_sources_user_id
    ON public.message_sources(user_id);

CREATE INDEX IF NOT EXISTS idx_message_sources_message_rank
    ON public.message_sources(message_id, rank);

-- user_sessions
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id
    ON public.user_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at
    ON public.user_sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_user_sessions_active
    ON public.user_sessions(user_id, expires_at)
    WHERE revoked_at IS NULL;

COMMIT;
