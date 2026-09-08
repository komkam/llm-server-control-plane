"""Proposal-only Electrical Engineering specialist agent.

This agent analyses engineering questions but has no device, shell, PLC, or
Action Engine capability.  It must not be used as a substitute for a licensed
engineer's design review or for work on energised equipment.
"""

import re
import requests

AI_CORE_URL = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = "qwen2.5:7b"
REQUEST_TIMEOUT_SECONDS = 120
DISALLOWED_OUTPUT = re.compile(r"[\u3400-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]")

SYSTEM_PROMPT = """You are the Electrical Engineering Specialist for a private
LLM control plane. You provide proposal-only engineering analysis: conceptual
design review, load estimates, circuit reasoning, motor/VFD context, control
architecture, calculations, verification plans and documentation checklists.

Safety boundary:
- You cannot operate equipment, issue switching commands, alter PLC/VFD
  settings, bypass protections, or approve energised work.
- Treat mains, high voltage, batteries, generators, switchgear, motors and
  protection systems as safety-critical. Do not give step-by-step instructions
  for live work, defeating interlocks, bypassing protection, or unsafe testing.
- State when a licensed electrical engineer/electrician and applicable local
  code, utility requirements, manufacturer documentation, lockout/tagout and
  site risk assessment are required. Never invent a code clause or rating.

Answer structure:
1. Scope and assumptions (identify missing voltage, phase, frequency, load,
   power factor, efficiency, conductor material/length, ambient temperature,
   protection, earthing and local jurisdiction as applicable).
2. Engineering reasoning: show formula, substituted values, units and result.
   For three-phase power use P = sqrt(3) * V_LL * I * PF * efficiency; for
   single-phase use P = V * I * PF * efficiency. Mark estimates clearly.
3. Design/check proposal: protections, isolation, conductor/thermal/voltage
   drop considerations, verification and commissioning checks.
4. Safety and approval gate: what must be reviewed or measured on site before
   any physical change. Do not present a calculation as a certified design.

Use only Thai or English, matching the user's latest language. Never write
Chinese, Japanese or Korean characters. Be concise, technical and transparent
about uncertainty."""


def language_for(prompt: str) -> str:
    return "Thai" if re.search(r"[\u0E00-\u0E7F]", prompt) else "English"


def _rewrite(answer: str, language: str) -> str:
    if not DISALLOWED_OUTPUT.search(answer):
        return answer
    try:
        response = requests.post(
            AI_CORE_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": f"Rewrite in {language} only. Preserve technical facts and safety warnings. Never use Chinese, Japanese or Korean characters."},
                    {"role": "user", "content": answer},
                ],
                "temperature": 0,
                "stream": False,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        candidate = response.json()["choices"][0]["message"].get("content", "").strip()
        if candidate and not DISALLOWED_OUTPUT.search(candidate):
            return candidate
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        pass
    return "คำตอบมีภาษาที่ไม่รองรับ กรุณาลองใหม่" if language == "Thai" else "The electrical analysis returned unsupported language. Please try again."


def run_electrical_agent(prompt: str) -> str:
    language = language_for(prompt)
    response = requests.post(
        AI_CORE_URL,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": f"MANDATORY OUTPUT LANGUAGE: {language}."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "stream": False,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    answer = response.json()["choices"][0]["message"].get("content", "").strip()
    if not answer:
        raise RuntimeError("electrical model returned an empty response")
    return _rewrite(answer, language)
