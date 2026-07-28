"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";
import { Brand } from "@/components/brand";
import {
  ChatIcon,
  CloseIcon,
  FolderIcon,
  HomeIcon,
  MenuIcon,
  PlusIcon,
  TrashIcon,
} from "@/components/icons";
import { LoadingScreen } from "@/components/loading-screen";
import { useAuth } from "@/lib/auth-context";
import { initials } from "@/lib/format";
import type { Conversation } from "@/lib/types";
import {
  deleteConversation,
  listConversations,
} from "@/lib/workspace-api";

const conversationChangedEvent = "documind:conversations-changed";

export function notifyConversationListChanged(conversation?: Conversation) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent<Conversation | undefined>(conversationChangedEvent, {
        detail: conversation,
      }),
    );
  }
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, status, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [router, status]);

  useEffect(() => setMobileOpen(false), [pathname]);

  const refreshConversations = useCallback(async () => {
    if (status !== "authenticated") return;

    setLoadingConversations(true);
    try {
      setConversations(await listConversations());
    } catch {
      // Conversation history is helpful but should never block the workspace.
    } finally {
      setLoadingConversations(false);
    }
  }, [status]);

  useEffect(() => {
    void refreshConversations();

    const handleChanged = (event: Event) => {
      const changedConversation = (
        event as CustomEvent<Conversation | undefined>
      ).detail;

      if (changedConversation) {
        setConversations((current) => [
          changedConversation,
          ...current.filter(
            (conversation) => conversation.id !== changedConversation.id,
          ),
        ]);
      }

      void refreshConversations();
    };

    window.addEventListener(conversationChangedEvent, handleChanged);
    return () => {
      window.removeEventListener(conversationChangedEvent, handleChanged);
    };
  }, [refreshConversations]);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
      router.replace("/login");
    } finally {
      setLoggingOut(false);
    }
  }

  async function handleDeleteConversation(
    event: MouseEvent<HTMLButtonElement>,
    conversationId: string,
  ) {
    event.preventDefault();
    event.stopPropagation();

    try {
      await deleteConversation(conversationId);
      setConversations((current) =>
        current.filter((conversation) => conversation.id !== conversationId),
      );

      const activeConversationId = new URLSearchParams(
        window.location.search,
      ).get("conversationId");

      if (activeConversationId === conversationId) {
        router.replace("/dashboard");
      }
    } catch {
      // The dashboard will show API errors when the user opens a chat.
    }
  }

  if (status !== "authenticated" || !user) {
    return <LoadingScreen />;
  }

  const nav = [
    { href: "/dashboard", label: "Ask DocuMind", icon: ChatIcon },
    { href: "/folders", label: "My folders", icon: FolderIcon },
  ];

  return (
    <div className="workspace-shell">
      <button
        aria-label="Open navigation"
        className="mobile-menu-button"
        onClick={() => setMobileOpen(true)}
        type="button"
      >
        <MenuIcon />
      </button>

      {mobileOpen && (
        <button
          aria-label="Close navigation"
          className="sidebar-scrim"
          onClick={() => setMobileOpen(false)}
          type="button"
        />
      )}

      <aside className={`workspace-sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand-row">
          <Brand />
          <button
            aria-label="Close navigation"
            className="icon-button sidebar-close"
            onClick={() => setMobileOpen(false)}
            type="button"
          >
            <CloseIcon />
          </button>
        </div>

        <Link className="new-chat-button" href="/dashboard">
          <PlusIcon />
          New chat
        </Link>

        <nav className="workspace-nav" aria-label="Workspace navigation">
          <p className="sidebar-label">Workspace</p>
          {nav.map((item) => {
            const Icon = item.icon;
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);

            return (
              <Link
                className={`workspace-nav-item ${active ? "is-active" : ""}`}
                href={item.href}
                key={item.href}
              >
                <Icon />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <section className="conversation-history" aria-label="Conversation history">
          <div className="conversation-history-heading">
            <p className="sidebar-label">Recent conversations</p>
            {loadingConversations && <span className="tiny-spinner" />}
          </div>

          <div className="conversation-history-list">
            {conversations.length === 0 && !loadingConversations ? (
              <p className="conversation-history-empty">Your saved chats will appear here.</p>
            ) : (
              conversations.slice(0, 20).map((conversation) => (
                <div className="conversation-history-item" key={conversation.id}>
                  <Link
                    className="conversation-history-link"
                    href={`/dashboard?conversationId=${encodeURIComponent(conversation.id)}`}
                    title={conversation.title || "Untitled conversation"}
                  >
                    <ChatIcon />
                    <span>{conversation.title || "Untitled conversation"}</span>
                  </Link>
                  <button
                    aria-label={`Delete ${conversation.title || "conversation"}`}
                    className="conversation-delete-button"
                    onClick={(event) =>
                      void handleDeleteConversation(event, conversation.id)
                    }
                    type="button"
                  >
                    <TrashIcon />
                  </button>
                </div>
              ))
            )}
          </div>
        </section>

        <div className="sidebar-tip">
          <HomeIcon />
          <div>
            <strong>Your private workspace</strong>
            <span>Files and chats are scoped to your account.</span>
          </div>
        </div>

        <div className="workspace-account">
          <div className="avatar">{initials(user.first_name, user.last_name)}</div>
          <div className="account-copy">
            <strong>{user.first_name} {user.last_name}</strong>
            <span>{user.email}</span>
          </div>
          <button
            className="sign-out-link"
            disabled={loggingOut}
            onClick={handleLogout}
            type="button"
          >
            {loggingOut ? "…" : "Sign out"}
          </button>
        </div>
      </aside>

      <main className="workspace-main">{children}</main>
    </div>
  );
}
