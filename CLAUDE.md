## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.

## Reglas del proyecto (definidas por el usuario)

1. **Graphify siempre al día.** Cada vez que haya una actualización del proyecto (código, documentación, merge, pull,
   cambio de rama), actualizar también el grafo: `graphify update .` (y `/graphify . --update` si cambian docs).
   El hook de git (`graphify hook install`) lo hace en commit y checkout, pero no sustituye correrlo tras editar.
2. **Desarrollo con spec-kit + superpowers.** Al desarrollar cualquier funcionalidad o cambio:
   - spec-kit: `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`
     (`/speckit-analyze` antes de implementar).
   - superpowers (`.claude/skills/`): `brainstorming` y `writing-plans` antes de codificar, `test-driven-development`
     al implementar, `systematic-debugging` ante fallos, `verification-before-completion` antes de dar algo por
     terminado y `requesting-code-review` al cerrar. Empezar leyendo `using-superpowers`.
