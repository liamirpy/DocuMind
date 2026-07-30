"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AppShell,
  notifyConversationListChanged,
} from "@/components/app-shell";
import { CitationAnswer } from "@/components/citation-answer";
import { PdfCitationViewer } from "@/components/pdf-citation-viewer";
import {
  ChevronIcon,
  FileIcon,
  FolderIcon,
  SendIcon,
  SparkIcon,
} from "@/components/icons";
import { ApiError } from "@/lib/auth-api";
import {
  cacheMessageSources,
  hydrateMessageSources,
} from "@/lib/citation-cache";
import { createId } from "@/lib/create-id";
import type {
  ChatScope,
  Conversation,
  ConversationMessage,
  Document,
  Folder,
  RagSource,
} from "@/lib/types";
import {
  askDocuments,
  getConversation,
  listDocuments,
  listFolders,
} from "@/lib/workspace-api";

const suggestions = [
  "Summarise the key ideas across my documents",
  "Which documents discuss the same topic?",
  "Create a short study guide from my files",
];

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedConversationId = searchParams.get("conversationId");
  const requestedDocumentId = searchParams.get("documentId");
  const requestedFolderId = searchParams.get("folderId");

  const [folders, setFolders] = useState<Folder[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const scopeRequestKey = requestedDocumentId
    ? `document:${requestedDocumentId}`
    : requestedFolderId
      ? `folder:${requestedFolderId}`
      : "all";
  const [scopeSelection, setScopeSelection] = useState<{
    requestKey: string;
    scope: ChatScope;
  } | null>(null);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [loadingLibrary, setLoadingLibrary] = useState(true);
  const [loadingConversation, setLoadingConversation] = useState(
    Boolean(requestedConversationId),
  );
  const [previousRequestedConversationId, setPreviousRequestedConversationId] =
    useState(requestedConversationId);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [activeSource, setActiveSource] = useState<RagSource | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  if (previousRequestedConversationId !== requestedConversationId) {
    setPreviousRequestedConversationId(requestedConversationId);
    setConversation(null);
    setMessages([]);
    setLoadingConversation(Boolean(requestedConversationId));
    setError("");
  }

  const refreshLibrary = useCallback(async (showLoader = false) => {
    try {
      const [folderRows, documentRows] = await Promise.all([
        listFolders(),
        listDocuments(),
      ]);
      setFolders(folderRows);
      setDocuments(documentRows);
    } catch (requestError) {
      if (showLoader) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load your library.",
        );
      }
    } finally {
      if (showLoader) setLoadingLibrary(false);
    }
  }, []);

  useEffect(() => {
    let active = true;

    void Promise.all([listFolders(), listDocuments()])
      .then(([folderRows, documentRows]) => {
        if (!active) return;
        setFolders(folderRows);
        setDocuments(documentRows);
      })
      .catch((requestError: unknown) => {
        if (!active) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load your library.",
        );
      })
      .finally(() => {
        if (active) setLoadingLibrary(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const hasProcessingDocuments = documents.some((document) =>
    ["uploaded", "queued", "processing"].includes(document.status),
  );

  useEffect(() => {
    if (!hasProcessingDocuments) return;

    const timer = window.setInterval(() => {
      void refreshLibrary(false);
    }, 4000);

    return () => window.clearInterval(timer);
  }, [hasProcessingDocuments, refreshLibrary]);

  const requestedScope = useMemo<ChatScope>(() => {
    if (requestedDocumentId) {
      const document = documents.find(
        (item) => item.id === requestedDocumentId,
      );

      if (document) {
        return {
          type: "document",
          documentId: document.id,
          label: document.original_filename,
        };
      }
    }

    if (requestedFolderId) {
      const folder = folders.find((item) => item.id === requestedFolderId);

      if (folder) {
        return { type: "folder", folderId: folder.id, label: folder.name };
      }
    }

    return { type: "all" };
  }, [documents, folders, requestedDocumentId, requestedFolderId]);

  const scope =
    scopeSelection?.requestKey === scopeRequestKey
      ? scopeSelection.scope
      : requestedScope;

  function selectScope(nextScope: ChatScope) {
    setScopeSelection({ requestKey: scopeRequestKey, scope: nextScope });
    setScopeOpen(false);
  }

  useEffect(() => {
    if (!requestedConversationId) return;

    let active = true;

    getConversation(requestedConversationId)
      .then((detail) => {
        if (!active) return;
        setConversation(detail.conversation);
        setMessages(
          hydrateMessageSources(
            detail.messages.filter(
              (message) =>
                message.role === "user" || message.role === "assistant",
            ),
          ),
        );
      })
      .catch((requestError: unknown) => {
        if (!active) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load this conversation.",
        );
        setConversation(null);
        setMessages([]);
      })
      .finally(() => {
        if (active) setLoadingConversation(false);
      });

    return () => {
      active = false;
    };
  }, [requestedConversationId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const scopeLabel = useMemo(() => {
    if (scope.type === "all") return "All my files";
    return scope.label;
  }, [scope]);

  async function submitQuestion(rawQuestion?: string) {
    const cleanQuestion = (rawQuestion ?? question).trim();
    if (!cleanQuestion || sending) return;




    const optimisticId = createId();

    setQuestion("");
    setError("");
    setSending(true);
    setMessages((current) => [
      ...current,
      { id: optimisticId, role: "user", content: cleanQuestion },
    ]);

    try {

      const response = await askDocuments(cleanQuestion, {
        documentId:
          scope.type === "document"
            ? scope.documentId
            : undefined,

        folderId:
          scope.type === "folder"
            ? scope.folderId
            : undefined,

        conversationId:
          conversation?.id ??
          requestedConversationId ??
          undefined,

      
      });

      const savedUserMessage = response.messages?.user;
      const responseSources = response.result?.sources ?? [];
      const savedAssistantMessage = response.messages?.assistant;
      const assistantMessage: ConversationMessage = savedAssistantMessage
        ? { ...savedAssistantMessage, sources: responseSources }
        : {
            id: createId(),
            role: "assistant",
            content: response.answer,
            sources: responseSources,
          };

      cacheMessageSources(assistantMessage.id, responseSources);

      setMessages((current) => {
        const withSavedUser = current.map((message) =>
          message.id === optimisticId && savedUserMessage
            ? savedUserMessage
            : message,
        );

        return [...withSavedUser, assistantMessage];
      });

      if (response.conversation) {
        setConversation(response.conversation);

        if (requestedConversationId !== response.conversation.id) {
          const nextParams = new URLSearchParams(searchParams.toString());
          nextParams.set("conversationId", response.conversation.id);
          router.replace(`/dashboard?${nextParams.toString()}`);
        }
      }

      notifyConversationListChanged(response.conversation);
    } catch (requestError) {
      const message =
        requestError instanceof ApiError
          ? requestError.message
          : "DocuMind could not answer that question.";
      setError(message);
    } finally {
      setSending(false);
    }
  }

  return (
    <AppShell>
      <section className="chat-page">
        <header className="topbar">
          <div>
            <p className="eyebrow">AI document workspace</p>
            <h1>{conversation?.title || "Ask your library"}</h1>
          </div>
          <div className="scope-picker-wrap">
            <button
              aria-expanded={scopeOpen}
              className="scope-picker"
              onClick={() => setScopeOpen((current) => !current)}
              type="button"
            >
              {scope.type === "folder" ? <FolderIcon /> : <FileIcon />}
              <span>
                <small>Talking to</small>
                <strong>{scopeLabel}</strong>
              </span>
              <ChevronIcon className={scopeOpen ? "rotate-90" : ""} />
            </button>

            {scopeOpen && (
              <div className="scope-menu">
                <button
                  className={scope.type === "all" ? "is-selected" : ""}
                  onClick={() => selectScope({ type: "all" })}
                  type="button"
                >
                  <FileIcon />
                  <span>
                    <strong>All my files</strong>
                    <small>Search your complete library</small>
                  </span>
                </button>

                {documents.map((document) => (
                  <button
                    className={
                      scope.type === "document" &&
                      scope.documentId === document.id
                        ? "is-selected"
                        : ""
                    }
                    key={document.id}
                    onClick={() =>
                      selectScope({
                        type: "document",
                        documentId: document.id,
                        label: document.original_filename,
                      })
                    }
                    type="button"
                  >
                    <FileIcon />
                    <span>
                      <strong>{document.original_filename}</strong>
                      <small>{document.status}</small>
                    </span>
                  </button>
                ))}

                {folders.map((folder) => (
                  <button
                    className={
                      scope.type === "folder" && scope.folderId === folder.id
                        ? "is-selected"
                        : ""
                    }
                    key={folder.id}
                    onClick={() =>
                      selectScope({
                        type: "folder",
                        folderId: folder.id,
                        label: folder.name,
                      })
                    }
                    type="button"
                  >
                    <FolderIcon />
                    <span>
                      <strong>{folder.name}</strong>
                      <small>Folder scope needs backend support</small>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </header>

        <div className={`chat-stage ${messages.length ? "has-messages" : ""}`}>
          {loadingConversation ? (
            <div className="library-loading page-centred">
              <div className="spinner" />
              <span>Loading conversation…</span>
            </div>
          ) : messages.length === 0 ? (
            <div className="chat-welcome">
              <div className="assistant-orb"><SparkIcon /></div>
              <h2>What would you like to understand?</h2>
              <p>
                Ask a question about one document or look for connections across
                your entire library. Your conversation will be saved automatically.
              </p>
              <div className="suggestion-grid">
                {suggestions.map((suggestion) => (
                  <button
                    disabled={loadingLibrary}
                    key={suggestion}
                    onClick={() => submitQuestion(suggestion)}
                    type="button"
                  >
                    <span>{suggestion}</span>
                    <ChevronIcon />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message) => (
                <article className={`message message-${message.role}`} key={message.id}>
                  <div className="message-avatar">
                    {message.role === "assistant" ? <SparkIcon /> : "You"}
                  </div>
                  <div>
                    <strong>{message.role === "assistant" ? "DocuMind" : "You"}</strong>
                    {message.role === "assistant" ? (
                      <CitationAnswer
                        content={message.content}
                        onOpenSource={setActiveSource}
                        sources={message.sources}
                      />
                    ) : (
                      <p>{message.content}</p>
                    )}
                  </div>
                </article>
              ))}
              {sending && (
                <article className="message message-assistant">
                  <div className="message-avatar"><SparkIcon /></div>
                  <div>
                    <strong>DocuMind</strong>
                    <div className="typing"><i /><i /><i /></div>
                  </div>
                </article>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="chat-composer-area">
          {error && <div className="inline-alert">{error}</div>}
          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void submitQuestion();
            }}
          >
            <textarea
              aria-label="Ask a question"
              disabled={sending || loadingConversation}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submitQuestion();
                }
              }}
              placeholder={`Ask ${scopeLabel} anything…`}
              rows={1}
              value={question}
            />
            <button
              aria-label="Send question"
              className="send-button"
              disabled={!question.trim() || sending || loadingConversation}
              type="submit"
            >
              <SendIcon />
            </button>
          </form>
          <p className="composer-note">
            Answers are generated from retrieved document text. Verify important details in the source file.
          </p>
        </div>
      </section>

      {activeSource && (
        <PdfCitationViewer
          document={documents.find(
            (item) => item.id === activeSource.documentId,
          )}
          onClose={() => setActiveSource(null)}
          source={activeSource}
        />
      )}
    </AppShell>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="loading-screen"><div className="spinner" /><p>Loading workspace…</p></div>}>
      <DashboardContent />
    </Suspense>
  );
}
