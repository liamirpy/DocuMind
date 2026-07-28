import { ApiError, apiFetch } from "@/lib/auth-api";
import type {
  Conversation,
  ConversationDetail,
  Document,
  Folder,
  FolderDetail,
  RagResponse,
  RagSource,
} from "@/lib/types";

async function readBody(response: Response): Promise<Record<string, unknown>> {
  const contentType = response.headers.get("content-type") ?? "";

  if (!contentType.includes("application/json")) {
    return {};
  }

  return (await response.json()) as Record<string, unknown>;
}

async function requireOk<T>(response: Response): Promise<T> {
  const body = await readBody(response);

  if (!response.ok) {
    const message =
      typeof body.error === "string"
        ? body.error
        : "The request could not be completed.";
    throw new ApiError(message, response.status);
  }

  return body as T;
}

export async function listFolders(): Promise<Folder[]> {
  const response = await apiFetch("/folders");
  const body = await requireOk<{ folders: Folder[] }>(response);
  return body.folders;
}

export async function createFolder(name: string): Promise<Folder> {
  const response = await apiFetch("/folders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const body = await requireOk<{ folder: Folder }>(response);
  return body.folder;
}

export async function renameFolder(
  folderId: string,
  name: string,
): Promise<Folder> {
  const response = await apiFetch(`/folders/${encodeURIComponent(folderId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const body = await requireOk<{ folder: Folder }>(response);
  return body.folder;
}

export async function deleteFolder(folderId: string): Promise<void> {
  const response = await apiFetch(`/folders/${encodeURIComponent(folderId)}`, {
    method: "DELETE",
  });
  await requireOk<Record<string, unknown>>(response);
}

export async function getFolder(folderId: string): Promise<FolderDetail> {
  const response = await apiFetch(`/folders/${encodeURIComponent(folderId)}`);
  return requireOk<FolderDetail>(response);
}

export async function listDocuments(): Promise<Document[]> {
  const response = await apiFetch("/documents");

  if (!response.ok) {
    await requireOk(response);
  }

  return (await response.json()) as Document[];
}

export async function uploadDocument(
  folderName: string,
  file: File,
): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetch(
    `/documents/upload/${encodeURIComponent(folderName)}`,
    {
      method: "POST",
      body: formData,
    },
  );
  const body = await requireOk<{ document: Document }>(response);
  return body.document;
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await apiFetch(
    `/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
  await requireOk<Record<string, unknown>>(response);
}

export async function renameDocument(
  documentId: string,
  filename: string,
): Promise<Document> {
  const response = await apiFetch(
    `/documents/${encodeURIComponent(documentId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    },
  );
  const body = await requireOk<{ document: Document }>(response);
  return body.document;
}

export async function downloadDocument(document: Document): Promise<void> {
  const response = await apiFetch(
    `/documents/${encodeURIComponent(document.id)}/download`,
  );

  if (!response.ok) {
    await requireOk(response);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = document.original_filename;
  window.document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}


export async function getDocumentArrayBuffer(
  documentId: string,
): Promise<ArrayBuffer> {
  const response = await apiFetch(
    `/documents/${encodeURIComponent(documentId)}/download`,
  );

  if (!response.ok) {
    await requireOk(response);
  }

  return response.arrayBuffer();
}

export async function listConversations(): Promise<Conversation[]> {
  const response = await apiFetch("/conversations");
  const body = await requireOk<{ conversations: Conversation[] }>(response);
  return body.conversations;
}

export async function getConversation(
  conversationId: string,
): Promise<ConversationDetail> {
  const response = await apiFetch(
    `/conversations/${encodeURIComponent(conversationId)}`,
  );
  return requireOk<ConversationDetail>(response);
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<Conversation> {
  const response = await apiFetch(
    `/conversations/${encodeURIComponent(conversationId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    },
  );
  const body = await requireOk<{ conversation: Conversation }>(response);
  return body.conversation;
}

export async function deleteConversation(
  conversationId: string,
): Promise<void> {
  const response = await apiFetch(
    `/conversations/${encodeURIComponent(conversationId)}`,
    { method: "DELETE" },
  );
  await requireOk<Record<string, unknown>>(response);
}

export async function askDocuments(
  question: string,
  options: {
    documentId?: string;
    folderId?: string;
    conversationId?: string;
  } = {},
): Promise<RagResponse> {
  const response = await apiFetch("/rag/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, ...options }),
  });

  const body = await requireOk<{
    answer: string | { answer?: string };
    conversation?: Conversation;
    messages?: RagResponse["messages"];
    result?: {
      context?: unknown;
      hits?: unknown[];
      sources?: RagSource[];
      [key: string]: unknown;
    };
  }>(response);

  const answer =
    typeof body.answer === "string"
      ? body.answer
      : typeof body.answer?.answer === "string"
        ? body.answer.answer
        : "DocuMind returned an empty answer.";

  return {
    answer,
    conversation: body.conversation,
    messages: body.messages,
    result: body.result,
  };
}
