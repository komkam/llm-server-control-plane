# Agent graph tools

The Diagnostic Agent has two local-only graph tools backed by NetworkX and
PyVis (sourced from their GitHub projects):

- `analyze_dependency_graph`: validates a bounded node/edge set and returns
  cycle detection, roots, leaves, topological order and Mermaid source.
- `render_dependency_graph`: performs the same analysis and writes a local,
  interactive HTML artifact under `apps/agent/data/graphs/`.

## Safety limits

Graph tools accept at most 80 nodes and 160 edges; every endpoint must appear
in the declared node list and identifiers are restricted to a small safe
character set. They have no network, shell, device-control, Action Engine or
approval capability.

## Example request

Ask `server-diagnostician` to analyse explicit nodes and edges, for example:

```text
Use graph tool: nodes = llm-gateway, qwen, electrical-engineer;
edges = llm-gateway -> qwen, electrical-engineer -> qwen.
Return cycles, roots, leaves and Mermaid source.
```

Generated HTML artifacts are local agent data. Dashboard publishing of an
artifact remains a separate, approval-gated feature.
