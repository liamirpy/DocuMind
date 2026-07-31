"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import {
  ChatIcon,
  ChevronIcon,
  EditIcon,
  FolderIcon,
  MoreIcon,
  PlusIcon,
  TrashIcon,
} from "@/components/icons";
import { Modal } from "@/components/modal";
import { ApiError } from "@/lib/auth-api";
import { formatDate } from "@/lib/format";
import type { Folder } from "@/lib/types";
import {
  createFolder,
  deleteFolder,
  listFolders,
  renameFolder,
} from "@/lib/workspace-api";

type DialogState =
  | { type: "closed" }
  | { type: "create" }
  | { type: "rename"; folder: Folder }
  | { type: "delete"; folder: Folder };

export default function FoldersPage() {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dialog, setDialog] = useState<DialogState>({ type: "closed" });
  const [folderName, setFolderName] = useState("");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listFolders()
      .then(setFolders)
      .catch((requestError: unknown) => {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load your folders.",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  function openCreate() {
    setFolderName("");
    setError("");
    setDialog({ type: "create" });
  }

  function openRename(folder: Folder) {
    setFolderName(folder.name);
    setError("");
    setDialog({ type: "rename", folder });
    setOpenMenuId(null);
  }

  async function saveFolder() {
    const cleanName = folderName.trim();
    if (!cleanName) return;

    setSaving(true);
    setError("");
    try {
      if (dialog.type === "create") {
        const folder = await createFolder(cleanName);
        setFolders((current) => [
          { ...folder, document_count: 0 },
          ...current,
        ]);
      } else if (dialog.type === "rename") {
        const folder = await renameFolder(dialog.folder.id, cleanName);
        setFolders((current) =>
          current.map((item) =>
            item.id === folder.id
              ? { ...item, ...folder }
              : item,
          ),
        );
      }
      setDialog({ type: "closed" });
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Could not save this folder.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (dialog.type !== "delete") return;

    setSaving(true);
    setError("");
    try {
      await deleteFolder(dialog.folder.id);
      setFolders((current) =>
        current.filter((item) => item.id !== dialog.folder.id),
      );
      setDialog({ type: "closed" });
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Could not delete this folder.",
      );
    } finally {
      setSaving(false);
    }
  }

  const isNameDialog = dialog.type === "create" || dialog.type === "rename";

  return (
    <AppShell>
      <section className="content-page">
        <header className="content-header">
          <div>
            <p className="eyebrow">Document library</p>
            <h1>My folders</h1>
            <p>Organise files into focused collections, then chat with them.</p>
          </div>
          <button className="button button-primary" onClick={openCreate} type="button">
            <PlusIcon />
            New folder
          </button>
        </header>

        {error && dialog.type === "closed" && <div className="page-alert">{error}</div>}

        {loading ? (
          <div className="library-loading"><div className="spinner" /><span>Loading folders…</span></div>
        ) : folders.length === 0 ? (
          <EmptyState
            action={<button className="button button-primary" onClick={openCreate} type="button"><PlusIcon />Create your first folder</button>}
            description="Create a folder for a project, course, client, or research topic."
            icon={<FolderIcon />}
            title="Your library is ready"
          />
        ) : (
          <div className="folder-grid">
            {folders.map((folder) => (
              <article className="folder-card" key={folder.id}>
                <div className="folder-card-top">
                  <div className="folder-symbol"><FolderIcon /></div>
                  <div className="menu-wrap">
                    <button
                      aria-label={`Actions for ${folder.name}`}
                      className="icon-button"
                      onClick={() => setOpenMenuId((current) => current === folder.id ? null : folder.id)}
                      type="button"
                    >
                      <MoreIcon />
                    </button>
                    {openMenuId === folder.id && (
                      <div className="action-menu">
                        <button onClick={() => openRename(folder)} type="button"><EditIcon />Rename</button>
                        <button
                          className="danger-action"
                          onClick={() => {
                            setDialog({ type: "delete", folder });
                            setOpenMenuId(null);
                            setError("");
                          }}
                          type="button"
                        ><TrashIcon />Delete</button>
                      </div>
                    )}
                  </div>
                </div>
                <Link className="folder-card-link" href={`/folders/${folder.id}`}>
                  <h2>{folder.name}</h2>
                  <p>{folder.document_count ?? 0} {(folder.document_count ?? 0) === 1 ? "file" : "files"}</p>
                  <div className="folder-meta">
                    <span>Created {formatDate(folder.created_at)}</span>
                    <ChevronIcon />
                  </div>
                </Link>
                <Link
                  className="folder-chat-link"
                  href={`/dashboard?folderId=${encodeURIComponent(folder.id)}`}
                >
                  <ChatIcon /> Chat with folder
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      <Modal
        description={dialog.type === "rename" ? "The folder and its stored files will keep the new name." : "Use a clear name that describes this collection."}
        onClose={() => !saving && setDialog({ type: "closed" })}
        open={isNameDialog}
        title={dialog.type === "rename" ? "Rename folder" : "Create a folder"}
      >
        <form
          className="modal-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveFolder();
          }}
        >
          <label className="field">
            <span>Folder name</span>
            <input
              autoFocus
              maxLength={100}
              onChange={(event) => setFolderName(event.target.value)}
              placeholder="e.g. Research papers"
              value={folderName}
            />
          </label>
          {error && <div className="form-alert">{error}</div>}
          <div className="modal-actions">
            <button className="button button-secondary" disabled={saving} onClick={() => setDialog({ type: "closed" })} type="button">Cancel</button>
            <button className="button button-primary" disabled={saving || !folderName.trim()} type="submit">{saving ? "Saving…" : dialog.type === "rename" ? "Save name" : "Create folder"}</button>
          </div>
        </form>
      </Modal>

      <Modal
        description="Only empty folders can be deleted. Delete its files first if necessary."
        onClose={() => !saving && setDialog({ type: "closed" })}
        open={dialog.type === "delete"}
        title="Delete folder?"
      >
        {dialog.type === "delete" && (
          <div className="modal-form">
            <div className="delete-summary"><FolderIcon /><span><strong>{dialog.folder.name}</strong><small>{dialog.folder.document_count ?? 0} files</small></span></div>
            {error && <div className="form-alert">{error}</div>}
            <div className="modal-actions">
              <button className="button button-secondary" disabled={saving} onClick={() => setDialog({ type: "closed" })} type="button">Cancel</button>
              <button className="button button-danger" disabled={saving} onClick={() => void confirmDelete()} type="button">{saving ? "Deleting…" : "Delete folder"}</button>
            </div>
          </div>
        )}
      </Modal>
    </AppShell>
  );
}
