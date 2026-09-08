"""Bounded, local-only dependency graph tools for the diagnostic agent."""

from __future__ import annotations

import html
import json
import re
import uuid
from pathlib import Path

import networkx as nx
from pyvis.network import Network

GRAPH_DIR = Path("/opt/llm-server/apps/agent/data/graphs")
MAX_NODES = 80
MAX_EDGES = 160
SAFE_ID = re.compile(r"^[A-Za-z0-9_.:/ -]{1,120}$")


def _clean_id(value: str) -> str:
    value = str(value).strip()
    if not SAFE_ID.fullmatch(value):
        raise ValueError("node identifiers may contain only letters, digits, spaces, . _ : / and -")
    return value


def _build(nodes: list[str], edges: list[dict], directed: bool) -> nx.Graph:
    if not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError(f"nodes must contain 1 to {MAX_NODES} items")
    if len(edges) > MAX_EDGES:
        raise ValueError(f"edges may contain at most {MAX_EDGES} items")
    cleaned = [_clean_id(node) for node in nodes]
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("node identifiers must be unique")
    graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_nodes_from(cleaned)
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("each edge must be an object with source and target")
        source, target = _clean_id(edge.get("source", "")), _clean_id(edge.get("target", ""))
        if source not in graph or target not in graph:
            raise ValueError("each edge source and target must be listed in nodes")
        graph.add_edge(source, target, label=_clean_id(edge.get("label", "depends_on")))
    return graph


def _mermaid(graph: nx.Graph, directed: bool) -> str:
    lines = ["flowchart LR"]
    for index, node in enumerate(graph.nodes):
        lines.append(f'  n{index}["{node.replace(chr(34), "")}"]')
    indexes = {node: index for index, node in enumerate(graph.nodes)}
    connector = "-->" if directed else "---"
    for source, target, data in graph.edges(data=True):
        lines.append(f"  n{indexes[source]} {connector}|{data['label']}| n{indexes[target]}")
    return "\n".join(lines)


def analyze_dependency_graph(nodes: list[str], edges: list[dict], directed: bool = True) -> dict:
    """Analyse a bounded local dependency graph and return cycles/topology/Mermaid."""
    graph = _build(nodes, edges, directed)
    if directed:
        cycles = [cycle for cycle in nx.simple_cycles(graph)][:20]
        topology = list(nx.topological_sort(graph)) if not cycles else None
        roots = [node for node, degree in graph.in_degree() if degree == 0]
        leaves = [node for node, degree in graph.out_degree() if degree == 0]
    else:
        cycles, topology = [], None
        roots = [node for node, degree in graph.degree() if degree <= 1]
        leaves = roots
    return {
        "directed": directed, "node_count": graph.number_of_nodes(), "edge_count": graph.number_of_edges(),
        "cycles": cycles, "topological_order": topology, "roots": roots, "leaves": leaves,
        "mermaid": _mermaid(graph, directed),
    }


def render_dependency_graph(nodes: list[str], edges: list[dict], directed: bool = True, title: str = "Dependency graph") -> dict:
    """Render a local interactive HTML graph; returns the artifact path and analysis."""
    graph = _build(nodes, edges, directed)
    analysis = analyze_dependency_graph(nodes, edges, directed)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    artifact = GRAPH_DIR / f"graph-{uuid.uuid4().hex}.html"
    network = Network(height="720px", width="100%", directed=directed, cdn_resources="in_line")
    network.set_options(json.dumps({"physics": {"enabled": True}, "interaction": {"hover": True}}))
    for node in graph.nodes:
        network.add_node(node, label=html.escape(node), title=html.escape(node))
    for source, target, data in graph.edges(data=True):
        network.add_edge(source, target, title=html.escape(data["label"]), label=html.escape(data["label"]))
    artifact.write_text(network.generate_html(notebook=False), encoding="utf-8")
    artifact.chmod(0o640)
    return {**analysis, "title": title[:120], "artifact": str(artifact)}
