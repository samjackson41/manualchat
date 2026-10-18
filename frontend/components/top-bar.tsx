"use client";

import Image from "next/image";
import { BookOpenIcon } from "lucide-react";
import logo from "@/assets/manual-chat-logo.svg";
import { useModelSelection } from "@/app/chat-runtime";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ManualUpload } from "@/components/manual-upload";
import { ThemeToggle } from "@/components/theme-toggle";
import { VehicleSelector } from "@/components/vehicle-selector";

export function TopBar({
  viewerOpen,
  onToggleViewer,
}: {
  viewerOpen: boolean;
  onToggleViewer: () => void;
}) {
  const { models, model, setModel } = useModelSelection();

  return (
    <header className="bg-topbar border-border flex flex-col border-b">
      <div className="flex items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <Image
            src={logo}
            alt="ManualChat"
            width={32}
            height={32}
            unoptimized
            className="size-8 shrink-0"
          />
          <VehicleSelector />
        </div>

        <div className="flex items-center gap-2">
          <ManualUpload />
          <Button
            variant={viewerOpen ? "secondary" : "outline"}
            aria-pressed={viewerOpen}
            onClick={onToggleViewer}
          >
            <BookOpenIcon /> Manual viewer
          </Button>
          <Select
            value={model}
            items={models.map((option) => ({
              value: option.id,
              label: option.label,
            }))}
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
                  <span className="block truncate">{option.label}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <ThemeToggle />
        </div>
      </div>
      <div
        aria-hidden="true"
        className="from-primary via-primary/40 h-0.5 bg-linear-to-r to-transparent"
      />
    </header>
  );
}
