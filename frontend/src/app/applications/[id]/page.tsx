"use client";

import { useParams, useRouter } from "next/navigation";
import { ApplicationDetail } from "@/components/ApplicationDetail";

export default function ApplicationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;

  if (!id) return null;

  return (
    <ApplicationDetail
      applicationId={id}
      onClose={() => router.back()}
    />
  );
}
