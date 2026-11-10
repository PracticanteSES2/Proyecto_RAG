"use client";

import { useCallback, useRef } from "react";
import { useApi } from "@/lib/api/contexto";
import { useChat } from "@/hooks/useChat";
import { usePreferencia } from "@/hooks/usePreferencia";
import { useSalud } from "@/hooks/useSalud";
import { useTema } from "@/hooks/useTema";
import { MenuAjustes } from "@/components/ui/MenuAjustes";
import { AvisoServidor } from "./AvisoServidor";
import { Compositor, type ManejadorCompositor } from "./Compositor";
import { Encabezado } from "./Encabezado";
import { EstadoVacio } from "./EstadoVacio";
import { Historial } from "./Historial";

/** Pantalla del chat: encabezado, aviso de servidor, historial (o bienvenida) y campo de pregunta. */
export function Chat() {
  const cliente = useApi();
  const [diagnostico, setDiagnostico] = usePreferencia<boolean>("asistente.diagnostico", false);
  const [tema, setTema] = useTema();
  const salud = useSalud(cliente);
  const { verificar } = salud;
  const alFallarRed = verificar;
  const chat = useChat({ cliente, diagnostico, alFallarRed });
  const compositor = useRef<ManejadorCompositor>(null);
  const ocupado = !!chat.activo;
  const vacio = chat.estado.mensajes.length === 0;

  const preguntar = useCallback(
    (texto: string, opcionId?: string) => {
      void chat.enviar(texto, opcionId);
      compositor.current?.enfocar();
    },
    [chat],
  );

  const nueva = () => {
    chat.nuevaConversacion();
    compositor.current?.enfocar();
  };

  return (
    <div className="flex h-dvh flex-col bg-bg">
      <Encabezado
        diagnostico={diagnostico}
        puedeReiniciar={!vacio}
        alNuevaConversacion={nueva}
        ajustes={
          <MenuAjustes
            tema={tema}
            alCambiarTema={setTema}
            diagnostico={diagnostico}
            alCambiarDiagnostico={setDiagnostico}
            puedeExportar={!!chat.estado.conversacionId && !vacio}
            alExportar={chat.exportar}
          />
        }
      />
      {salud.estado === "caido" && <AvisoServidor alReintentar={salud.verificar} />}

      <main className="min-h-0 flex-1 overflow-y-auto [scrollbar-gutter:stable]">
        <div className="mx-auto w-full max-w-[var(--chat-max-width)] px-4 pb-6 pt-6">
          {vacio ? (
            <EstadoVacio cliente={cliente} alPreguntar={(t) => preguntar(t)} deshabilitado={ocupado} />
          ) : (
            <Historial
              estado={chat.estado}
              diagnostico={diagnostico}
              ocupado={ocupado}
              alElegirOpcion={(id, texto) => preguntar(texto, id)}
              alReintentar={chat.reintentar}
              alCalificar={(id, valor, comentario) => void chat.calificar(id, valor, comentario)}
            />
          )}
        </div>
      </main>

      <footer className="shrink-0 bg-linear-to-t from-bg from-70% to-transparent">
        <div className="mx-auto w-full max-w-[var(--chat-max-width)] px-4 pb-3 pt-2">
          <Compositor ref={compositor} ocupado={ocupado} alEnviar={(t) => preguntar(t)} alDetener={chat.detener} />
          <p className="mt-2 text-center text-xs text-fg-muted">
            Respondo solo con información de los tableros y documentos institucionales.
          </p>
        </div>
      </footer>
    </div>
  );
}
