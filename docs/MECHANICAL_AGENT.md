# Mechanical Engineering Agent

The Mechanical Engineering Agent is a proposal-only specialist available at
`127.0.0.1:5302` and through the LLM Gateway with model
`mechanical-engineer`.

It supports conceptual design review, statics, rotating equipment, machine
elements, materials, thermal/fluids/HVAC context, vibration, maintenance and
verification planning. It has no capability to control machinery, PLCs,
interlocks, pressure systems, deployments or approvals.

## Example

```bash
curl -sS http://127.0.0.1:5000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "mechanical-engineer",
    "messages": [{"role": "user", "content": "What data is required to estimate shaft torque for a 15 kW motor at 1450 rpm?"}],
    "stream": false
  }'
```

## Mandatory review boundary

Responses are preliminary engineering analysis, not certified designs. Before
physical work, obtain applicable drawings, site measurements, manufacturer
limits, materials data, inspection/testing requirements and review by a
qualified mechanical engineer and competent site personnel. Never use it to
bypass guards or interlocks, direct work on moving/pressurised/hot equipment,
or replace a site safety plan.

## Knowledge base

Store only approved, versioned drawings, manuals, data sheets and standards
extracts under `apps/mechanical-engineer/knowledge/`. They are not model context
until a retrieval pipeline is separately reviewed and approved.
