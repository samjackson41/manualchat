"use client";

import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useModelSelection } from "./chat-runtime";

export default function Home() {
  const { models, model, setModel } = useModelSelection();

  return (
    <main className="mx-auto flex h-dvh max-w-3xl flex-col px-4">
      <header className="flex items-center justify-between py-4">
        <h1 className="text-lg font-semibold">ManualChat</h1>
        <Select
          value={model}
          onValueChange={(value) => {
            if (value) setModel(value);
          }}
        >
          <SelectTrigger aria-label="Model selector" className="w-44">
            <SelectValue placeholder="Pick a model" />
          </SelectTrigger>
          <SelectContent>
            {models.map((option) => (
              <SelectItem key={option.id} value={option.id}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </header>

      <section className="flex min-h-0 flex-1 flex-col">
        <Thread />
      </section>
    </main>
  );
}