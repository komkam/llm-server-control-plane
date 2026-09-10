"""Read-only semantic intent classifier for the LLM Gateway."""

import os
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

MODEL_ID = os.getenv("EMBEDDING_CLASSIFIER_MODEL", "Qwen/Qwen3-Embedding-0.6B")
MODEL_REVISION = os.getenv("EMBEDDING_CLASSIFIER_REVISION") or None
MIN_SCORE = float(os.getenv("EMBEDDING_CLASSIFIER_MIN_SCORE", "0.62"))
MIN_MARGIN = float(os.getenv("EMBEDDING_CLASSIFIER_MIN_MARGIN", "0.08"))

# Human-maintained routing policy. Add examples when a route is corrected.
INTENT_EXAMPLES = {
    "server-diagnostician": (
        "ตรวจสอบสถานะ server และ service ที่ล้มเหลว",
        "วิเคราะห์ CPU RAM disk Docker logs และ health check",
        "diagnose a failed deployment, service, or system health problem",
    ),
    "electrical-engineer": (
        "คำนวณกำลังไฟฟ้าสามเฟส สายไฟ เบรกเกอร์ และแรงดันตก",
        "วิเคราะห์วงจรไฟฟ้า VFD มอเตอร์ หม้อแปลง และ protection relay",
        "เลือก contactor fuse overload relay starter และตู้ควบคุมมอเตอร์",
        "What contactor rating should I select for an electrical control panel?",
        "calculate three phase power, cable size, breaker, voltage drop, or VFD",
    ),
    "mechanical-engineer": (
        "คำนวณปั๊ม วาล์ว แรงบิดเพลา แบริ่ง เกียร์ และการสั่นสะเทือน",
        "วิเคราะห์ระบบเครื่องกล HVAC ไฮดรอลิก นิวเมติก และการไหล",
        "calculate pump sizing, shaft torque, bearing load, vibration, or HVAC flow",
    ),
    "qwen-engineer": (
        "คำถามทั่วไป การเขียน การสรุป และการอธิบายแนวคิด",
        "general question, writing, explanation, programming, or conversation",
    ),
}

model: SentenceTransformer | None = None
prototypes: dict[str, np.ndarray] = {}


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


def load_model() -> None:
    global model, prototypes
    model = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION, device="cpu")
    prototypes = {}
    for route, examples in INTENT_EXAMPLES.items():
        vectors = model.encode(list(examples), normalize_embeddings=True, convert_to_numpy=True)
        centroid = np.mean(vectors, axis=0)
        prototypes[route] = centroid / np.linalg.norm(centroid)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_model()
    yield


app = FastAPI(title="LLM Gateway Embedding Classifier", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok" if model is not None else "starting",
        "model": MODEL_ID,
        "device": "cpu",
        "routes": sorted(prototypes),
    }


@app.post("/v1/classify")
def classify(request: ClassifyRequest):
    if model is None or not prototypes:
        raise HTTPException(status_code=503, detail="classifier model is not ready")
    vector = model.encode(request.text, normalize_embeddings=True, convert_to_numpy=True)
    ranked = sorted(
        ((route, float(np.dot(vector, prototype))) for route, prototype in prototypes.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    best_route, best_score = ranked[0]
    second_score = ranked[1][1]
    margin = best_score - second_score
    specialist = best_route != "qwen-engineer"
    accepted = specialist and best_score >= MIN_SCORE and margin >= MIN_MARGIN
    return {
        "route": best_route if accepted else "qwen-engineer",
        "accepted": accepted,
        "best_route": best_route,
        "score": round(best_score, 4),
        "margin": round(margin, 4),
        "thresholds": {"min_score": MIN_SCORE, "min_margin": MIN_MARGIN},
        "scores": {route: round(score, 4) for route, score in ranked},
    }
