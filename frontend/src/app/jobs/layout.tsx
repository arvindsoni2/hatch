import type { Metadata } from "next";
import { PRODUCT_ROUTES } from "@/lib/product-routes";

export const metadata: Metadata = {
  title: `${PRODUCT_ROUTES.jobs.label} | Hatch`,
  description: PRODUCT_ROUTES.jobs.purpose,
};

export default function JobsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
