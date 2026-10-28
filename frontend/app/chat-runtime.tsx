"use client";

import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  useRemoteThreadListRuntime,
  type ChatModelAdapter,
  type TextMessagePart,
  type ThreadAssistantMessagePart,
  type ThreadUserMessage,
  type ToolCallMessagePart,
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
import { chatStream, getModels, type ModelOption } from "@/lib/api";
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

// Parse a tool-call argument string into the object shape the tool-call part
// stores. Invalid or non-object JSON falls back to an empty object.
function parseToolArgs(text: string): ToolCallMessagePart["args"] {
  try {
    const value: unknown = JSON.parse(text);
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return value as ToolCallMessagePart["args"];
    }
  } catch {
    // Fall through to the empty default below.
  }
  return {};
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

// Generates a title for a new thread from its first message.
const titleGenerator = createSimpleTitleAdapter();

// The localStorage prefix that scopes chat history to one vehicle. Threads
// and messages live under `manualchat:vehicle:<id>:`, so each vehicle keeps its
// own history. The `default` bucket holds chats made with no vehicle selected.
const threadListPrefix = (vehicleId: string | null) =>
  `manualchat:vehicle:${vehicleId ?? "default"}:`;

export function ChatRuntimeProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState<string>("");
  // The adapter is created once, so it reads live values through refs.
  const modelRef = useRef(model);
  modelRef.current = model;
  const { activeVehicleId } = useVehicles();
  const vehicleRef = useRef(activeVehicleId);
  vehicleRef.current = activeVehicleId;

  // A new adapter per vehicle. Swapping it reloads the thread list and resets
  // the active thread, so switching vehicles shows that vehicle's history.
  const threadListAdapter = useMemo(
    () =>
      createLocalStorageAdapter({
        storage,
        prefix: threadListPrefix(activeVehicleId),
        titleGenerator,
      }),
    [activeVehicleId],
  );

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
      async *run({ messages, abortSignal }) {
        // The backend /chat/stream takes a single query. Send the latest user
        // turn; multi-turn context is left to the backend memory work.
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

        const toolCalls: ToolCallMessagePart[] = [];
        const toolIndexById = new Map<string, number>();
        let answer = "";

        // The message content is the full current snapshot: the tool calls so
        // far, followed by the answer text once it starts streaming.
        const snapshot = (): ThreadAssistantMessagePart[] => {
          const parts: ThreadAssistantMessagePart[] = [...toolCalls];
          if (answer !== "") parts.push({ type: "text", text: answer });
          return parts;
        };

        for await (const event of chatStream(
          {
            query,
            model: modelRef.current || undefined,
            vehicleId: vehicleRef.current || undefined,
          },
          abortSignal,
        )) {
          if (abortSignal.aborted) return;
          switch (event.type) {
            case "tool_call": {
              toolIndexById.set(event.tool_call_id, toolCalls.length);
              toolCalls.push({
                type: "tool-call",
                toolCallId: event.tool_call_id,
                toolName: event.tool_name,
                args: parseToolArgs(event.args_text),
                argsText: event.args_text,
              });
              yield { content: snapshot() };
              break;
            }
            case "tool_result": {
              const index = toolIndexById.get(event.tool_call_id);
              if (index !== undefined) {
                toolCalls[index] = {
                  ...toolCalls[index],
                  result: event.result,
                  isError: event.error,
                };
              }
              yield { content: snapshot() };
              break;
            }
            case "token":
              answer += event.content;
              yield { content: snapshot() };
              break;
            case "done":
              // Tokens have already accumulated; keep the answer if the stream
              // sent a done event without any token (a robustness guard).
              if (answer === "" && event.content !== "") {
                answer = event.content;
                yield { content: snapshot() };
              }
              break;
            case "error":
              throw new Error(event.message);
          }
        }
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
