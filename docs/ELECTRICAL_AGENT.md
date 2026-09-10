# Electrical Engineering Agent

The Electrical Engineering Agent is a proposal-only specialist. It is available
locally at `127.0.0.1:5301` and through the LLM Gateway by explicitly
selecting model `electrical-engineer`.

It can help with conceptual design review, load estimation, single/three-phase
reasoning, motor/VFD context, verification plans and documentation checklists.
It has no shell, Action Engine, PLC, VFD, switching, device-control, deployment
or approval capability.

## Example

```bash
curl -sS http://127.0.0.1:5000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "electrical-engineer",
    "messages": [{"role": "user", "content": "Estimate three-phase load current for 15 kW, 400 V, PF 0.85, efficiency 0.90."}],
    "stream": false
  }'
```

## Mandatory review boundary

Its calculations are estimates, not certified designs. Before physical work,
require the relevant local code, site survey, manufacturer documentation,
equipment ratings, protection/coordination study, lockout/tagout procedure and
a licensed electrical engineer or electrician as applicable. It must not be
used for energised work, bypassing protection, changing live equipment or
issuing switching commands.

## Knowledge base

Place reviewed, versioned reference material only under
`apps/electrical-engineer/knowledge/`. The initial release does not ingest this
directory automatically. A retrieval pipeline must be separately reviewed and
approved before those materials become model context.
