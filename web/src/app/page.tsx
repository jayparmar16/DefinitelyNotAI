import { AuthGate } from "@/components/AuthGate";
import { ChatApp } from "@/components/ChatApp";

export default function Home() {
  return (
    <AuthGate>
      <ChatApp />
    </AuthGate>
  );
}
