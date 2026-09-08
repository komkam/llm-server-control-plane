"""Proposal-only Mechanical Engineering specialist agent."""

import re
import requests

AI_CORE_URL = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = "qwen2.5:7b"
TIMEOUT = 120
CJK = re.compile(r"[\u3400-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]")

SYSTEM_PROMPT = """You are a Mechanical Engineering Specialist. Provide
proposal-only analysis for conceptual design review, statics, machine elements,
materials, heat transfer, fluids, HVAC context, vibration, rotating equipment,
maintenance planning and verification checklists.

Safety boundary:
- You have no capability to operate equipment, alter machine/PLC settings,
  bypass guards/interlocks, issue lifting or pressure-system instructions, or
  approve work. Do not provide procedures for energised, moving, pressurised,
  hot, confined-space or hazardous work.
- Never invent a material property, code clause, load rating, fatigue life or
  safety factor. Require manufacturer data, site measurement and applicable
  local standards. Escalate safety-critical work to a qualified mechanical
  engineer and competent site personnel.

Use this response structure:
1. Scope and assumptions; state missing loads, geometry, material, temperature,
   pressure, speed, duty cycle, environment, constraints and jurisdiction.
2. Engineering reasoning; show formulas, value substitution, SI units and
   uncertainty. Clearly label preliminary estimates.
3. Design/check proposal; identify failure modes, thermal/stress/deflection,
   vibration, sealing, lubrication, guarding, inspection and maintainability
   considerations as relevant.
4. Verification and safety gate; identify drawings, manufacturer limits,
   inspection/testing and professional approval required before physical work.

Answer only in Thai or English, matching the user's latest language. Never
write Chinese, Japanese or Korean characters. A calculation is not a certified
design and must not be presented as one."""


def language_for(prompt: str) -> str:
    return "Thai" if re.search(r"[\u0E00-\u0E7F]", prompt) else "English"


def run_mechanical_agent(prompt: str) -> str:
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
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    answer = response.json()["choices"][0]["message"].get("content", "").strip()
    if not answer:
        raise RuntimeError("mechanical model returned an empty response")
    if not CJK.search(answer):
        return answer
    return "คำตอบมีภาษาที่ไม่รองรับ กรุณาลองใหม่" if language == "Thai" else "The mechanical analysis returned unsupported language. Please try again."
