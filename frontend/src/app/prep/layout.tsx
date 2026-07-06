import type { Metadata } from "next";
import { PRODUCT_ROUTES } from "@/lib/product-routes";

export const metadata: Metadata = {
  title: `${PRODUCT_ROUTES.interviewPrep.label} | Hatch`,
  description: PRODUCT_ROUTES.interviewPrep.purpose,
};

export default function InterviewPrepLayout({ children }: { children: React.ReactNode }) {
  return children;
}
