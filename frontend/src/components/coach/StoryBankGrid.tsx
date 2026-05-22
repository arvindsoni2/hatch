"use client";

import { StoryListItem } from "@/lib/api";
import { StoryCard } from "./StoryCard";
import { BookOpen } from "lucide-react";

interface Props {
  stories: StoryListItem[];
  onSelect: (id: string) => void;
}

export function StoryBankGrid({ stories, onSelect }: Props) {
  if (stories.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-500">
        <BookOpen className="h-12 w-12 mb-4 opacity-30" />
        <p className="text-lg font-medium">No stories yet</p>
        <p className="text-sm mt-1">Add your first STAR story to get started.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {stories.map((story) => (
        <StoryCard key={story.id} story={story} onClick={() => onSelect(story.id)} />
      ))}
    </div>
  );
}
