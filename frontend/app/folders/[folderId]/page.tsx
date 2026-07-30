"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import {
  ChatIcon,
  ChevronIcon,
  DownloadIcon,
  EditIcon,
  FileIcon,
  FolderIcon,
  MoreIcon,
  TrashIcon,
  UploadIcon,
} from "@/components/icons";
import { Modal } from "@/components/modal";
import { ApiError } from "@/lib/auth-api";
import { formatBytes, formatDate } from "@/lib/format";
import type { Document, FolderDetail } from "@/lib/types";
import {
  deleteDocument,
  downloadDocument,
  getFolder,
  renameDocument,
  uploadDocument,
} from "@/lib/workspace-api";

type DocumentDialog =
  | { type: "closed" }
  | { type: "rename"; document: Document }
  | { type: "delete"; document: Document };

export default function FolderDetailPage() {
  const params = useParams<{ folderId: string }>();
  const folderId = params.folderId;
  const inputRef = useRef<HTMLInputElement>(null);
  const [data, setData] = useState<FolderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [dialog, setDialog] = useState<DocumentDialog>({ type: "closed" });
  const [filename, setFilename] = useState("");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadFolder = useCallback(async () => {
    try {
      const nextData = await getFolder(folderId);
      setData(nextData);
      setError("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load this folder.");
    } finally {
      setLoading(false);
    }
  }, [folderId]);

  useEffect(() => {
    void loadFolder();
  }, [loadFolder]);

  const hasProcessingDocuments = data?.documents.some((document) =>
    ["uploaded", "queued", "processing"].includes(document.status),
  ) ?? false;

  useEffect(() => {
    if (!hasProcessingDocuments) return;

    const timer = window.setInterval(() => {
      void getFolder(folderId)
        .then(setData)
        .catch(() => {
          // Keep the current folder visible if a background refresh fails.
        });
    }, 4000);

    return () => window.clearInterval(timer);
  }, [folderId, hasProcessingDocuments]);

  async function uploadFiles(files: FileList | File[]) {
    if (!data || files.length === 0) return;

    setUploading(true);
    setError("");
    setNotice("");
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(data.folder.name, file);
      }
      setNotice(`${files.length} ${files.length === 1 ? "file" : "files"} uploaded successfully.`);
      await loadFolder();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "The upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function confirmDelete() {
    if (dialog.type !== "delete") return;
    setSaving(true);
    setError("");
    try {
      await deleteDocument(dialog.document.id);
      setData((current) => current ? { ...current, documents: current.documents.filter((item) => item.id !== dialog.document.id) } : current);
      setDialog({ type: "closed" });
      setNotice("File deleted.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not delete this file.");
    } finally {
      setSaving(false);
    }
  }

  async function confirmRename() {
    if (dialog.type !== "rename" || !filename.trim()) return;
    setSaving(true);
    setError("");
    try {
      const updated = await renameDocument(dialog.document.id, filename.trim());
      setData((current) => current ? { ...current, documents: current.documents.map((item) => item.id === updated.id ? { ...item, ...updated } : item) } : current);
      setDialog({ type: "closed" });
      setNotice("File renamed.");
    } catch (requestError) {
      const message = requestError instanceof ApiError && requestError.status === 404
        ? "Your backend does not have PATCH /api/documents/:documentId yet. Add the route from BACKEND-NOTES.md."
        : requestError instanceof Error ? requestError.message : "Could not rename this file.";
      setError(message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <AppShell><div className="library-loading page-centred"><div className="spinner" /><span>Opening folder…</span></div></AppShell>;
  }

  if (!data) {
    return (
      <AppShell>
        <section className="content-page">
          <EmptyState action={<Link className="button button-secondary" href="/folders">Back to folders</Link>} description={error || "This folder is unavailable."} icon={<FolderIcon />} title="Folder not found" />
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <section className="content-page">
        <div className="breadcrumbs">
          <Link href="/folders">My folders</Link>
          <ChevronIcon />
          <span>{data.folder.name}</span>
        </div>

        <header className="content-header folder-detail-header">
          <div>
            <p className="eyebrow">Folder</p>
            <h1>{data.folder.name}</h1>
            <p>{data.documents.length} {data.documents.length === 1 ? "file" : "files"} in this collection</p>
          </div>
          <div className="header-actions">
            <Link className="button button-secondary" href={`/dashboard?folderId=${encodeURIComponent(data.folder.id)}`}><ChatIcon />Chat with folder</Link>
            <button className="button button-primary" onClick={() => inputRef.current?.click()} type="button"><UploadIcon />Upload files</button>
            <input
              accept=".pdf,.txt,.json,.nii,.nii.gz"
              hidden
              multiple
              onChange={(event) => event.target.files && void uploadFiles(event.target.files)}
              ref={inputRef}
              type="file"
            />
          </div>
        </header>

        {error && <div className="page-alert">{error}</div>}
        {notice && <div className="page-notice">{notice}</div>}

        <button
          className={`upload-dropzone ${dragging ? "is-dragging" : ""}`}
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={(event) => { event.preventDefault(); setDragging(false); }}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void uploadFiles(event.dataTransfer.files);
          }}
          type="button"
        >
          <UploadIcon />
          <span><strong>{uploading ? "Uploading files…" : "Drop files here or browse"}</strong><small>PDF, TXT, JSON, NII or NII.GZ · maximum 10 MB each</small></span>
        </button>

        {data.documents.length === 0 ? (
          <EmptyState action={<button className="button button-primary" onClick={() => inputRef.current?.click()} type="button"><UploadIcon />Choose a file</button>} description="Upload a PDF or another supported file to start building this collection." icon={<FileIcon />} title="This folder is empty" />
        ) : (
          <div className="document-table-wrap">
            <table className="document-table">
              <thead><tr><th>Name</th><th>Status</th><th>Size</th><th>Uploaded</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {data.documents.map((document) => (
                  <tr key={document.id}>
                    <td>
                      <Link className="document-name" href={`/dashboard?documentId=${encodeURIComponent(document.id)}`}>
                        <span className="file-type-badge">{document.file_type.toUpperCase()}</span>
                        <span><strong>{document.original_filename}</strong><small>Click to chat with this file</small></span>
                      </Link>
                    </td>
                    <td><span className={`status-pill status-${document.status}`}>{document.status}</span></td>
                    <td>{formatBytes(document.file_size_bytes)}</td>
                    <td>{formatDate(document.uploaded_at)}</td>
                    <td>
                      <div className="menu-wrap table-menu">
                        <button aria-label={`Actions for ${document.original_filename}`} className="icon-button" onClick={() => setOpenMenuId((current) => current === document.id ? null : document.id)} type="button"><MoreIcon /></button>
                        {openMenuId === document.id && (
                          <div className="action-menu action-menu-right">
                            <Link href={`/dashboard?documentId=${encodeURIComponent(document.id)}`}><ChatIcon />Chat</Link>
                            <button onClick={() => { void downloadDocument(document).catch((requestError: unknown) => setError(requestError instanceof Error ? requestError.message : "Download failed.")); setOpenMenuId(null); }} type="button"><DownloadIcon />Download</button>
                            <button onClick={() => { setFilename(document.original_filename); setDialog({ type: "rename", document }); setOpenMenuId(null); setError(""); }} type="button"><EditIcon />Rename</button>
                            <button className="danger-action" onClick={() => { setDialog({ type: "delete", document }); setOpenMenuId(null); setError(""); }} type="button"><TrashIcon />Delete</button>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Modal description="Keep the file extension, for example .pdf." onClose={() => !saving && setDialog({ type: "closed" })} open={dialog.type === "rename"} title="Rename file">
        <form className="modal-form" onSubmit={(event) => { event.preventDefault(); void confirmRename(); }}>
          <label className="field"><span>Filename</span><input autoFocus onChange={(event) => setFilename(event.target.value)} value={filename} /></label>
          {error && <div className="form-alert">{error}</div>}
          <div className="modal-actions"><button className="button button-secondary" disabled={saving} onClick={() => setDialog({ type: "closed" })} type="button">Cancel</button><button className="button button-primary" disabled={saving || !filename.trim()} type="submit">{saving ? "Renaming…" : "Rename file"}</button></div>
        </form>
      </Modal>

      <Modal description="This permanently removes the stored file and its indexed document data." onClose={() => !saving && setDialog({ type: "closed" })} open={dialog.type === "delete"} title="Delete file?">
        {dialog.type === "delete" && (
          <div className="modal-form">
            <div className="delete-summary"><FileIcon /><span><strong>{dialog.document.original_filename}</strong><small>{formatBytes(dialog.document.file_size_bytes)}</small></span></div>
            {error && <div className="form-alert">{error}</div>}
            <div className="modal-actions"><button className="button button-secondary" disabled={saving} onClick={() => setDialog({ type: "closed" })} type="button">Cancel</button><button className="button button-danger" disabled={saving} onClick={() => void confirmDelete()} type="button">{saving ? "Deleting…" : "Delete file"}</button></div>
          </div>
        )}
      </Modal>
    </AppShell>
  );
}
