"""CLI del doctor.

  python -m tools.doctor                    # backend + frontend
  python -m tools.doctor backend            # solo Python/FastAPI
  python -m tools.doctor frontend           # solo Next.js/TypeScript
  python -m tools.doctor --verificar        # trinquete contra tools/doctor/linea_base.json
  python -m tools.doctor --actualizar-linea-base
  python -m tools.doctor --json | --md informe.md | --todo | --cambios origin/desarrollo

Códigos de salida: 0 bien · 1 el trinquete falló (o se negó a bajar el listón) ·
2 error de uso (p. ej. sin línea base) · 3 con --estricto, algo de la línea base no se pudo verificar.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from tools.doctor import linea_base as lb
from tools.doctor.config import RUTA_REGLAS, cargar_config
from tools.doctor.modelo import CATEGORIAS, PERFILES, Hallazgo, Informe, InformePerfil
from tools.doctor.motor import analizar_todo

RAIZ_DEFECTO = Path(__file__).resolve().parents[2]


def _banda(p: float | None) -> str:
    if p is None:
        return "sin medir"
    return "bien" if p >= 75 else ("necesita trabajo" if p >= 50 else "crítico")


def _barra(p: float) -> str:
    llenos = int(round(p / 10))
    return "#" * llenos + "." * (10 - llenos)


def _fmt(p: float | None) -> str:
    return "  —  " if p is None else f"{p:5.1f}"


def top(hallazgos: list[Hallazgo], n: int) -> list[Hallazgo]:
    """Los más graves primero, rotando entre reglas para no repetir la misma."""
    grupos: dict[tuple, list[Hallazgo]] = {}
    for h in hallazgos:  # ya vienen ordenados por severidad
        grupos.setdefault((h.severidad, h.categoria, h.regla), []).append(h)
    salida: list[Hallazgo] = []
    ronda = 0
    while len(salida) < n and any(len(g) > ronda for g in grupos.values()):
        for sev in ("alta", "media", "baja"):
            for clave, grupo in grupos.items():
                if clave[0] == sev and len(grupo) > ronda and len(salida) < n:
                    salida.append(grupo[ronda])
        ronda += 1
    orden = {"alta": 0, "media": 1, "baja": 2}
    return sorted(salida, key=lambda h: orden[h.severidad])


def _archivos_cambiados(raiz: Path, ref: str) -> set[str] | None:
    try:
        diff = subprocess.run(["git", "-C", str(raiz), "-c", "core.quotepath=false", "diff", "--name-only", ref],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        nuevos = subprocess.run(["git", "-C", str(raiz), "-c", "core.quotepath=false", "ls-files", "-o", "--exclude-standard"],
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if diff.returncode != 0:
        return None
    return {p for p in (diff.stdout + nuevos.stdout).splitlines() if p}


def _filtrar(hallazgos: list[Hallazgo], cambiados: set[str] | None) -> list[Hallazgo]:
    if cambiados is None:
        return hallazgos
    return [h for h in hallazgos if any(c == h.archivo or c.startswith(h.archivo + "/") for c in cambiados)]


def _texto_perfil(inf: InformePerfil, n_top: int, todo: bool, cambiados: set[str] | None) -> list[str]:
    nombres = CATEGORIAS[inf.perfil]
    if inf.omitido:
        return [f"{inf.perfil.upper()}: omitido — {'; '.join(inf.avisos)}", ""]
    m = inf.metricas
    det = f"{m.get('archivos', 0)} archivos"
    if "modulos_python" in m:
        det += f", {m['modulos_python']} módulos .py"
    det += f", {m.get('segundos', 0)} s"
    lineas = [f"{inf.perfil.upper()}  {_fmt(inf.puntaje)}/100  ({_banda(inf.puntaje)}; {det})"]
    for cat, nombre in nombres.items():
        hs = [h for h in inf.hallazgos if h.categoria == cat]
        if cat in inf.puntajes:
            p = inf.puntajes[cat]
            altas = sum(1 for h in hs if h.severidad == "alta")
            lineas.append(f"  {nombre:<24} {_fmt(p)}  {_barra(p)}  {len(hs):>4} hallazgos ({altas} altos)")
        else:
            lineas.append(f"  {nombre:<24}   —    omitida: {inf.omitidas.get(cat, '')}")
    legado = m.get("legado") or {}
    if legado:
        lineas.append("  Legado (se tolera, no debe crecer): " + ", ".join(
            f"{r} {v['archivos']} arch./{v['lineas']} lín." for r, v in legado.items()))
    visibles = _filtrar(inf.hallazgos, cambiados)
    lista = visibles if todo else top(visibles, n_top)
    if lista:
        titulo = "Hallazgos" if todo else f"Top {len(lista)} problemas"
        if cambiados is not None:
            titulo += " (solo archivos cambiados)"
        lineas += ["", f"  {titulo}:"]
        for h in lista:
            lineas.append(f"  [{h.severidad}] {h.categoria}/{h.regla}  {h.ubicacion}")
            lineas.append(f"      {h.mensaje}")
            lineas.append(f"      -> {h.sugerencia}")
    if inf.externos:
        cuenta: dict[str, int] = {}
        for e in inf.externos:
            cuenta[e.herramienta] = cuenta.get(e.herramienta, 0) + 1
        lineas += ["", "  Externas (informativo, no puntúa): " + ", ".join(f"{k} {v}" for k, v in cuenta.items())]
        for e in inf.externos[: (len(inf.externos) if todo else 5)]:
            lineas.append(f"    {e.herramienta} {e.codigo} {e.archivo}:{e.linea} {e.mensaje}")
    for a in inf.avisos:
        lineas.append(f"  Aviso: {a}")
    return lineas + [""]


def texto(informe: Informe, n_top: int = 10, todo: bool = False, cambiados: set[str] | None = None) -> str:
    lineas = [
        "Doctor de salud del proyecto",
        f"Puntaje global: {_fmt(informe.puntaje_global).strip()}/100 ({_banda(informe.puntaje_global)})",
        "",
    ]
    for inf in informe.perfiles.values():
        lineas += _texto_perfil(inf, n_top, todo, cambiados)
    return "\n".join(lineas)


def markdown(informe: Informe, n_top: int = 30) -> str:
    l = ["# Doctor de salud del proyecto", "",
         f"**Puntaje global: {_fmt(informe.puntaje_global).strip()}/100** ({_banda(informe.puntaje_global)})", ""]
    for inf in informe.perfiles.values():
        l.append(f"## {inf.perfil.capitalize()} — {_fmt(inf.puntaje).strip()}/100")
        l.append("")
        if inf.omitido:
            l += [f"_Omitido_: {'; '.join(inf.avisos)}", ""]
            continue
        l += ["| Categoría | Puntaje | Hallazgos | Altos |", "|---|---:|---:|---:|"]
        for cat, nombre in CATEGORIAS[inf.perfil].items():
            hs = [h for h in inf.hallazgos if h.categoria == cat]
            p = f"{inf.puntajes[cat]:.1f}" if cat in inf.puntajes else f"omitida ({inf.omitidas.get(cat, '')})"
            l.append(f"| {nombre} | {p} | {len(hs)} | {sum(1 for h in hs if h.severidad == 'alta')} |")
        l += ["", f"### Top {n_top}", "", "| Sev. | Regla | Ubicación | Problema | Sugerencia |", "|---|---|---|---|---|"]
        for h in top(inf.hallazgos, n_top):
            l.append(f"| {h.severidad} | {h.categoria}/{h.regla} | `{h.ubicacion}` | {h.mensaje.replace('|', '/')} | {h.sugerencia.replace('|', '/')} |")
        if inf.avisos:
            l += ["", *(f"- {a}" for a in inf.avisos)]
        l.append("")
    return "\n".join(l)


def _texto_verificacion(v: lb.Verificacion) -> str:
    l = ["", "Verificación contra la línea base (trinquete):"]
    if v.ok:
        l.append("  OK: ningún puntaje bajó y no hay hallazgos altos nuevos.")
    for f in v.fallos:
        l.append(f"  FALLA: {f}")
    otros = [(p, h) for p, h in v.nuevos if h.severidad != "alta"]
    if otros:
        l.append(f"  Hallazgos nuevos no altos ({len(otros)}):")
        for p, h in otros[:20]:
            l.append(f"    [{h.severidad}] {p}/{h.categoria}/{h.regla} {h.ubicacion} — {h.mensaje}")
    for a in v.avisos:
        l.append(f"  Aviso: {a}")
    if v.mejoras:
        l.append("  Mejoras: " + "; ".join(v.mejoras))
        if v.ok:
            l.append("  El puntaje subió: sube el listón con `python -m tools.doctor --actualizar-linea-base`.")
    if not v.ok:
        l.append("  Corrige los problemas nuevos (o el retroceso) antes de integrar. Ver docs/calidad/doctor.md.")
    return "\n".join(l)


def _argumentos(argv):
    p = argparse.ArgumentParser(prog="python -m tools.doctor", description="Puntaje de salud del proyecto con trinquete.")
    p.add_argument("perfil", nargs="?", choices=[*PERFILES, "todos"], default="todos")
    p.add_argument("--raiz", type=Path, default=RAIZ_DEFECTO)
    p.add_argument("--config", type=Path)
    p.add_argument("--linea-base", type=Path)
    p.add_argument("--json", action="store_true", help="informe JSON por stdout")
    p.add_argument("--md", type=Path, help="escribe el informe en Markdown")
    p.add_argument("--todo", action="store_true", help="lista todos los hallazgos")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--cambios", metavar="REF", help="muestra solo hallazgos de archivos cambiados respecto de REF")
    p.add_argument("--verificar", action="store_true", help="falla si se baja del listón")
    p.add_argument("--actualizar-linea-base", action="store_true", help="sube el listón al estado actual")
    p.add_argument("--forzar", action="store_true", help="con --actualizar-linea-base: acepta aunque empeore")
    p.add_argument("--estricto", action="store_true", help="con --verificar: falla si algo no se pudo verificar")
    p.add_argument("--sin-externas", action="store_true", help="no corre ruff/vulture/tsc/eslint/react-doctor")
    return p.parse_args(argv)


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args = _argumentos(argv)
    raiz = args.raiz.resolve()
    ruta_config = args.config or (raiz / "tools" / "doctor" / "reglas.toml")
    config = cargar_config(ruta_config if ruta_config.exists() else RUTA_REGLAS)
    ruta_base = args.linea_base or (raiz / "tools" / "doctor" / "linea_base.json")
    base = lb.cargar(ruta_base)
    perfiles = PERFILES if args.perfil == "todos" else (args.perfil,)

    if args.verificar and base is None:
        print(f"No hay línea base en {ruta_base}. Créala con --actualizar-linea-base.", file=sys.stderr)
        return 2

    informe = analizar_todo(raiz, config, perfiles, externas=not args.sin_externas, linea_base=base)
    tolerancia = float(config["general"]["tolerancia"])
    verificacion = lb.comparar(informe, base, tolerancia) if base and (args.verificar or args.actualizar_linea_base) else None
    cambiados = _archivos_cambiados(raiz, args.cambios) if args.cambios else None

    codigo = 0
    if args.json:
        datos = informe.a_dict()
        if verificacion is not None and args.verificar:
            datos["verificacion"] = verificacion.a_dict()
        print(json.dumps(datos, ensure_ascii=False, indent=1))
    else:
        print(texto(informe, args.top, args.todo, cambiados))
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(markdown(informe), encoding="utf-8")

    if args.verificar:
        if not args.json:
            print(_texto_verificacion(verificacion))
        if not verificacion.ok:
            codigo = 1
        elif args.estricto and verificacion.sin_verificar:
            print("Con --estricto: hay partes de la línea base sin verificar.", file=sys.stderr)
            codigo = 3

    if args.actualizar_linea_base:
        if verificacion is not None and not verificacion.ok and not args.forzar:
            print(_texto_verificacion(verificacion))
            print("No se actualiza: el listón solo sube. Corrige o usa --forzar si el retroceso es consciente.")
            return 1
        lb.guardar(ruta_base, lb.crear(informe, base))
        print(f"Línea base actualizada en {ruta_base}.")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
