import type { Metadata } from "next";

import { AdminApp } from "@/components/admin/AdminApp";

export const metadata: Metadata = { title: "AskWRI admin" };

export default function AdminPage() {
  return <AdminApp />;
}
