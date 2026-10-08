"""
Smoke test end-to-end del chatbot SIN Power BI / Ollama / Qdrant.

Uso (desde la raíz del repo):
  python -m tests.sim.run_smoke [--quiet] [--mode app|master] [--case NOMBRE ...]
                                [--list] [--ollama-down] [--powerbi-down] [--json RUTA]

  --quiet        oculta los print internos del proyecto (recomendado)
  --mode master  desactiva QueryPlanBuilder para ejercitar MasterMetric/Legacy
  --case X       corre solo el caso X (se puede repetir o separar con comas)
"""
import argparse
import contextlib
import io
import json
import sys

sys.dont_write_bytecode = True

from . import harness
from .cases import CASES

SHOW_KEYS = ("status", "route", "stage", "metric", "metric_id", "dashboard", "semantic_model", "value",
             "clarification_options", "question")


def summarize(result):
    out = {k: result.get(k) for k in SHOW_KEYS if result.get(k) not in (None, [], "")}
    if result.get("dax"):
        out["dax"] = result["dax"]
    if result.get("filters"):
        out["filters"] = [{k: f.get(k) for k in ("type", "table", "column", "value", "year", "month")
                           if f.get(k) is not None} for f in result["filters"]]
    details = result.get("details")
    if isinstance(details, dict):
        out["details"] = {k: details.get(k) for k in
                          ("status", "reason", "requested_value", "unresolved_text", "requested_dimension",
                           "requested_year", "requested_month", "error", "error_type")
                          if details.get(k) is not None}
    if result.get("error"):
        out["error"] = result["error"]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["app", "master"], default="app")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--case", action="append", default=[])
    ap.add_argument("--list", action="store_true", help="lista los casos y sale")
    ap.add_argument("--ollama-down", action="store_true")
    ap.add_argument("--powerbi-down", action="store_true")
    ap.add_argument("--json", help="guarda el reporte completo en esta ruta")
    args = ap.parse_args(argv)

    if args.list:
        for name, case in CASES.items():
            print(f"{name:28s} {case['label']}")
        return 0

    names = [n for item in args.case for n in item.split(",") if n] or list(CASES)
    unknown = [n for n in names if n not in CASES]
    if unknown:
        print("Casos desconocidos:", ", ".join(unknown), "| usa --list")
        return 2

    sink = io.StringIO()
    with contextlib.redirect_stdout(sink if args.quiet else sys.stdout):
        engine, cm, formatter, ollama_status, pbi, _ = harness.build_engine(
            ollama_up=not args.ollama_down, powerbi_up=not args.powerbi_down, quiet=args.quiet)
    if args.mode == "master":
        engine.query_plan_builder = None

    report = {"mode": args.mode, "ollama": ollama_status.get("status"),
              "powerbi": pbi.get("status"), "cases": {}}
    print("=" * 100)
    print(f"BUILD ok | ollama={ollama_status.get('status')} | powerbi={pbi.get('status')} | mode={args.mode}")
    for name in names:
        case = CASES[name]
        print("=" * 100)
        print(f"CASO {name}: {case['label']}")
        steps = []
        for text, result, ui in harness.run_case(case, engine, cm, formatter):
            sim = result.get("_sim", {})
            step = {"message": text, **summarize(result), "ui": ui,
                    "type_mismatch": [m["message"] for m in sim.get("type_mismatch", [])],
                    "queries": [{k: v for k, v in q.items() if k != "type_mismatch"}
                                for q in sim.get("dax_log", [])]}
            steps.append(step)
            print("-" * 100)
            print(f"> {text}")
            for k in SHOW_KEYS + ("filters", "details", "error"):
                if k in step:
                    print(f"    {k}: {step[k]}")
            if "dax" in step:
                print("    dax: " + step["dax"].replace("\n", "\n         "))
            print(f"    UI> {ui!r}"[:600])
            for w in step["type_mismatch"]:
                print(f"    !! {w}")
            if sim.get("exception"):
                print("    !! EXCEPCIÓN:", sim["exception"])
                print(sim["traceback"])
        report["cases"][name] = steps
    print("=" * 100)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
        print("Reporte JSON:", args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
