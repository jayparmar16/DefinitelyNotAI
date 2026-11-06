import type { Metadata } from "next";

import { AdminApp } from "@/components/admin/AdminApp";
import { AuthGate } from "@/components/AuthGate";

export const metadata: Metadata = { title: "AskWRI admin" };

export default function AdminPage() {
  return (
    <AuthGate>
      <AdminApp />
    </AuthGate>
  );
}
