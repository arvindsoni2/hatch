import type { Metadata } from "next";
import { PRODUCT_ROUTES } from "@/lib/product-routes";

export const metadata: Metadata = {
  title: `${PRODUCT_ROUTES.pipeline.label} | Hatch`,
  description: PRODUCT_ROUTES.pipeline.purpose,
};

export default function PipelineLayout({ children }: { children: React.ReactNode }) {
  return children;
}
