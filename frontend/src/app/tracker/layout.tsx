import type { Metadata } from "next";
import { PRODUCT_ROUTES } from "@/lib/product-routes";

export const metadata: Metadata = {
  title: `${PRODUCT_ROUTES.applications.label} | Hatch`,
  description: PRODUCT_ROUTES.applications.purpose,
};

export default function ApplicationsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
