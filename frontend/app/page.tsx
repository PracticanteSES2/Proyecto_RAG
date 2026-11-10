import { Chat } from "@/components/chat/Chat";
import { ProveedorApi } from "@/lib/api/contexto";

export default function Pagina() {
  return (
    <ProveedorApi>
      <Chat />
    </ProveedorApi>
  );
}
