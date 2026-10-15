"use client";

import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  useRemoteThreadListRuntime,
  type ChatModelAdapter,
  type TextMessagePart,
  type ThreadUserMessage,
} from "@assistant-ui/react";
import {
  createLocalStorageAdapter,
  createSimpleTitleAdapter,
  type AsyncStorageLike,
} from "@assistant-ui/core/react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export type ModelOption = { id: string; label: string };

type ModelSelection = {
  models: ModelOption[];
  model: string;
  setModel: (id: string) => void;
};

const ModelSelectionContext = createContext<ModelSelection | null>(null);

export function useModelSelection(): ModelSelection {
  const ctx = useContext(ModelSelectionContext);
  if (!ctx) {
    throw new Error("useModelSelection must be used inside ChatRuntimeProvider");
  }
  return ctx;
}

type ChatResponse = { reply: string };

// The browser localStorage behind the async interface the adapter expects.
const storage: AsyncStorageLike = {
  getItem: (key) => Promise.resolve(localStorage.getItem(key)),
  setItem: (key, value) => {
    localStorage.setItem(key, value);
    return Promise.resolve();
  },
  removeItem: (key) => {
    localStorage.removeItem(key);
    return Promise.resolve();
  },
};

// One adapter instance for the whole app. It persists thread metadata and
// per-thread messages to localStorage under the `manualchat:` prefix.
const threadListAdapter = createLocalStorageAdapter({
  storage,
  prefix: "manualchat:",
  titleGenerator: createSimpleTitleAdapter(),
});

export function ChatRuntimeProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState<string>("");
  // The adapter is created once, so it reads the live model through this ref.
  const modelRef = useRef(model);
  modelRef.current = model;

  useEffect(() => {
    fetch(`${BACKEND_URL}/models`)
      .then((res) => res.json())
      .then((data: { default: string; options: ModelOption[] }) => {
        setModels(data.options);
        setModel(data.default);
      })
      .catch(() => {
        // The model list is optional; an empty selector still sends no override.
      });
  }, []);

  const chatModelAdapter = useMemo<ChatModelAdapter>(
    () => ({
      async run({ messages, abortSignal }) {
        // The backend /chat takes a single query. Send the latest user turn;
        // multi-turn context is left to the backend memory work.
        const lastUser = [...messages]
          .reverse()
          .find(
            (message): message is ThreadUserMessage => message.role === "user",
          );
        const query = lastUser
          ? lastUser.content
              .filter((part): part is TextMessagePart => part.type === "text")
              .map((part) => part.text)
              .join("\n")
          : "";

        const res = await fetch(`${BACKEND_URL}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            model: modelRef.current || undefined,
          }),
          signal: abortSignal,
        });

        if (!res.ok) {
          const data = await res.json().catch(() => null);
          const detail =
            data && typeof data.detail === "string" ? data.detail : null;
          throw new Error(detail ?? `Request failed (${res.status})`);
        }

        const data: ChatResponse = await res.json();
        return { content: [{ type: "text" as const, text: data.reply }] };
      },
    }),
    [],
  );

  const runtimeHook = useCallback(
    () => useLocalRuntime(chatModelAdapter),
    [chatModelAdapter],
  );

  const runtime = useRemoteThreadListRuntime({
    runtimeHook,
    adapter: threadListAdapter,
  });

  const selection = useMemo<ModelSelection>(
    () => ({ models, model, setModel }),
    [models, model],
  );

  return (
    <ModelSelectionContext.Provider value={selection}>
      <AssistantRuntimeProvider runtime={runtime}>
        {children}
      </AssistantRuntimeProvider>
    </ModelSelectionContext.Provider>
  );
}
