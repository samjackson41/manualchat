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
import { chat, getModels, type ModelOption } from "@/lib/api";
import { useVehicles } from "./vehicle-runtime";

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
  // The adapter is created once, so it reads live values through refs.
  const modelRef = useRef(model);
  modelRef.current = model;
  const { activeVehicleId } = useVehicles();
  const vehicleRef = useRef(activeVehicleId);
  vehicleRef.current = activeVehicleId;

  useEffect(() => {
    getModels()
      .then((data) => {
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

        const res = await chat(
          {
            query,
            model: modelRef.current || undefined,
            vehicleId: vehicleRef.current || undefined,
          },
          abortSignal,
        );

        return { content: [{ type: "text" as const, text: res.reply }] };
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
