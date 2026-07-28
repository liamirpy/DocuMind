import type { ConversationMessage, RagSource } from "@/lib/types";

const STORAGE_KEY = "documind:message-sources:v1";
const MAX_CACHED_MESSAGES = 200;

type SourceCache = Record<string, RagSource[]>;

function readCache(): SourceCache {
  if (typeof window === "undefined") return {};

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};

    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as SourceCache) : {};
  } catch {
    return {};
  }
}

function writeCache(cache: SourceCache): void {
  if (typeof window === "undefined") return;

  try {
    const entries = Object.entries(cache);
    const trimmed = entries.slice(Math.max(0, entries.length - MAX_CACHED_MESSAGES));
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(trimmed)));
  } catch {
    // Citation caching is a progressive enhancement. The chat still works
    // when localStorage is disabled or full.
  }
}

export function cacheMessageSources(messageId: string, sources: RagSource[]): void {
  if (!messageId || sources.length === 0) return;

  const cache = readCache();
  delete cache[messageId];
  cache[messageId] = sources;
  writeCache(cache);
}

export function getCachedMessageSources(messageId: string): RagSource[] {
  return readCache()[messageId] ?? [];
}

export function hydrateMessageSources(
  messages: ConversationMessage[],
): ConversationMessage[] {
  const cache = readCache();

  return messages.map((message) => {
    if (message.sources?.length) return message;

    const cachedSources = cache[message.id];
    return cachedSources?.length ? { ...message, sources: cachedSources } : message;
  });
}
