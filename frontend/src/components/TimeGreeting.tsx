"use client";

import { useEffect, useState } from "react";

function getGreeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Good morning";
  if (hour >= 12 && hour < 17) return "Good afternoon";
  if (hour >= 17 && hour < 21) return "Good evening";
  return "Good night";
}

export function TimeGreeting({ name }: { name?: string | null }) {
  const [greeting, setGreeting] = useState<string>("Welcome");

  useEffect(() => {
    setGreeting(getGreeting(new Date().getHours()));
  }, []);

  const suffix = name ? `, ${name.split(" ")[0]}.` : ".";
  return <>{greeting + suffix}</>;
}
