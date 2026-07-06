import type { Metadata } from "next";
import { PRODUCT_ROUTES } from "@/lib/product-routes";

export const metadata: Metadata = {
  title: `${PRODUCT_ROUTES.interviewCoach.label} | Hatch`,
  description: PRODUCT_ROUTES.interviewCoach.purpose,
};

export default function InterviewCoachLayout({ children }: { children: React.ReactNode }) {
  return children;
}
