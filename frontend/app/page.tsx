"use client";

import { useCallback, useEffect, useState } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type ModelOption = { id: string; label: string };
type Message = { role: "user" | "assistant"; content: string };

export default function Home() {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [query, setQuery] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  // Load the model list once; the dropdown default mirrors the backend default.
  useEffect(() => {
    fetch(`${BACKEND_URL}/models`)
      .then((res) => res.json())
      .then((data: { default: string; options: ModelOption[] }) => {
        setModels(data.options);
        setSelected(data.default);
      })
      .catch((err) => setError(`Failed to load models: ${err.message}`));
  }, []);

  const send = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setQuery("");
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, model: selected }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Request failed (${res.status})`);
      }
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [query, loading, selected]);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-4 p-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">ManualChat</h1>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
          aria-label="Model selector"
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </header>

      <section className="flex flex-1 flex-col gap-3 rounded border border-gray-200 p-4">
        {messages.length === 0 && (
          <p className="text-sm text-gray-400">
            Ask a question about your manual. (Reply comes through the LangGraph graph.)
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded px-3 py-2 text-sm ${
              m.role === "user"
                ? "self-end bg-blue-500 text-white"
                : "self-start bg-gray-100 text-gray-900"
            }`}
          >
            {m.content}
          </div>
        ))}
        {loading && <p className="text-sm text-gray-400">Thinking…</p>}
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="flex gap-2"
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. What's the oil drain bolt torque?"
          className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded bg-blue-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </main>
  );
}