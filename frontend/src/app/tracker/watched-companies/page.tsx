import { serverApiFetch } from "@/lib/server-api";
import { WatchedCompaniesClient, type CompanyWatchlistItem } from "./WatchedCompaniesClient";

export const revalidate = 0;

export default async function WatchedCompaniesPage() {
  const data = await serverApiFetch<{ items: CompanyWatchlistItem[]; total: number }>("/api/watchlist/companies");
  return <WatchedCompaniesClient initialItems={data.items} initialTotal={data.total} />;
}
