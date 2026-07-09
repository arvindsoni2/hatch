import { serverApiFetch } from "@/lib/server-api";
import { QuestionBankClient, type QuestionBankItem } from "./QuestionBankClient";

export const revalidate = 0;

export default async function QuestionBankPage() {
  const data = await serverApiFetch<{ items: QuestionBankItem[]; total: number }>("/api/question-bank");
  return <QuestionBankClient initialItems={data.items} initialTotal={data.total} />;
}
