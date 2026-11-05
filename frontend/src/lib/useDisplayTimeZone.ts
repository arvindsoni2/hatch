"use client";

import { useEffect, useState } from "react";
import { fetchDisplayTimeZone } from "@/lib/coachReadinessApi";
import { browserTimeZone } from "@/lib/formatInterviewTime";

/** Configured display zone, else the browser zone. */
export function useDisplayTimeZone(): string {
  const [timeZone, setTimeZone] = useState(browserTimeZone);

  useEffect(() => {
    let active = true;
    fetchDisplayTimeZone().then((configured) => {
      if (active && configured) setTimeZone(configured);
    });
    return () => {
      active = false;
    };
  }, []);

  return timeZone;
}
