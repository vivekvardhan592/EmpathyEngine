# backend/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, conlist, constr,Field
from typing import List, Dict, Any,Annotated
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import torch.nn.functional as F 
import time
from collections import Counter

# -----------------------------
# FastAPI app initialization
# -----------------------------
app = FastAPI(
    title="Empathy Engine API",
    description="Backend for emotion analysis of chat messages",
    version="1.1.0"
)

# -----------------------------
# CORS: allow frontend to call this API
# -----------------------------
origins = [
    "http://localhost:3000",  # React dev server
    "http://127.0.0.1:3000",
    "*"  # you can restrict later if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Load emotion model & tokenizer
# -----------------------------
MODEL_NAME = "SamLowe/roberta-base-go_emotions"
MIN_CONFIDENCE = 0.  # below this, we treat as "uncertain/neutral"

print("🔁 Loading model... This may take some time on first run.")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
model.eval()

id2label = model.config.id2label  # mapping: index -> emotion label


# -----------------------------
# Pydantic models (request/response)
# -----------------------------
# Each message: non-empty string, max 500 chars
MessageType = constr(strip_whitespace=True, min_length=1, max_length=500)

class ChatRequest(BaseModel):
    messages: Annotated[
        List[str],
        Field(min_length=1, max_length=50, description="List of messages")
    ]


class TimelineItem(BaseModel):
    text: str
    emotion: str
    score: float

class AnalyzeResponse(BaseModel):
    timeline: List[TimelineItem]
    summary: str
    emotional_trend: str            # ⭐ NEW
    processing_time_ms: float
    emotion_distribution: Dict[str, int]    # how long the analysis took


# -----------------------------
# Helper: analyze a single message
# -----------------------------
def analyze_single_message(text: str) -> Dict[str, Any]:
    """
    Run the transformer model on a single message and return
    the top emotion + score. Includes a confidence threshold.
    """
    if not text.strip():
        return {
            "text": text,
            "emotion": "neutral",
            "score": 0.0
        }

    try:
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=128
        )

        # Move tensors to device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits  # shape: [1, num_labels]
            probs = F.softmax(logits, dim=-1)

        # Get top emotion
        top_prob, top_id = torch.max(probs, dim=-1)
        emotion_label = id2label[int(top_id)]
        score = float(top_prob.item())

        # Apply confidence threshold
        if score < MIN_CONFIDENCE:
            emotion_label = "uncertain"  # or "neutral"

        return {
            "text": text,
            "emotion": emotion_label,
            "score": round(score, 4)
        }

    except Exception as e:
        # Fallback: never crash the whole request because of one bad message
        print(f"⚠️ Error analyzing message: {e}")
        return {
            "text": text,
            "emotion": "error",
            "score": 0.0
        }


# -----------------------------
# Helper: generate emotional summary
# -----------------------------
def generate_summary(timeline: List[TimelineItem]) -> str:
    if not timeline:
        return "No messages were provided, so no emotional signal could be detected."

    # Filter out items where emotion is "error"
    valid_items = [item for item in timeline if item.emotion not in ("error", "uncertain")]
    if not valid_items:
        return (
            "The model could not confidently determine emotions from the provided "
            "messages. The emotional signal appears very weak or ambiguous."
        )

    # Count emotions
    from collections import Counter
    emotion_counts = Counter(item.emotion for item in valid_items)
    total = len(valid_items)

    # Top emotions
    most_common = emotion_counts.most_common(3)

    # Build a simple, readable summary
    summary_lines = []

    # Overall dominant emotion
    if most_common:
        primary_emotion, count = most_common[0]
        pct = (count / total) * 100
        summary_lines.append(
            f"The dominant emotion in this conversation is **{primary_emotion}** (~{pct:.1f}% of the confidently detected messages)."
        )

    # Other strong emotions
    if len(most_common) > 1:
        others = []
        for emotion, count in most_common[1:]:
            pct = (count / total) * 100
            others.append(f"{emotion} (~{pct:.1f}%)")
        summary_lines.append(
            "Other noticeable emotions include: " + ", ".join(others) + "."
        )

    # Emotional intensity hint
    avg_score = sum(item.score for item in valid_items) / total
    if avg_score > 0.8:
        intensity_text = "Emotions are expressed very strongly and consistently."
    elif avg_score > 0.6:
        intensity_text = "Emotions are fairly strong and noticeable throughout."
    else:
        intensity_text = "Emotions are present but somewhat mixed or mild."

    summary_lines.append(intensity_text)

    # Closing line
    summary_lines.append(
        "This analysis can support more empathetic responses and better understanding "
        "of the user's emotional state over time."
    )

    return " ".join(summary_lines)


def generate_emotional_trend(timeline: List[TimelineItem]) -> str:
    if len(timeline) < 2:
        return "Not enough messages to determine an emotional trend."

    # Extract emotions at key points
    start_emotion = timeline[0].emotion
    middle_emotion = timeline[len(timeline) // 2].emotion
    end_emotion = timeline[-1].emotion

    # Build the trend sentence
    trend = (
        f"The conversation begins with {start_emotion}, "
        f"shifts to {middle_emotion} in the middle, "
        f"and ends with {end_emotion}."
    )

    # If start and end are different, mention emotional change
    if start_emotion != end_emotion:
        trend += f" This indicates an emotional shift from {start_emotion} to {end_emotion}."

    return trend

# -----------------------------
# Health check endpoints
# -----------------------------
@app.get("/", tags=["Health"])
def root():
    return {
        "status": "ok",
        "message": "Empathy Engine backend is running.",
    }


@app.get("/health/model", tags=["Health"])
def model_health():
    """
    Simple endpoint to show model + device info for debugging / judges.
    """
    return {
        "model_name": MODEL_NAME,
        "device": str(device),
        "num_labels": model.config.num_labels,
        "loaded": True
    }


# -----------------------------
# Main API: /analyze-chat
# -----------------------------
@app.post("/analyze-chat", response_model=AnalyzeResponse, tags=["Analysis"])
def analyze_chat(request: ChatRequest):
    """
    Analyze a list of chat messages and return:
    - timeline: emotion + score for each message
    - summary: overall emotional summary
    - processing_time_ms: how long the analysis took
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="At least one message is required.")

    start_time = time.perf_counter()

    timeline_raw: List[Dict[str, Any]] = []

    try:
        for msg in request.messages:
            result = analyze_single_message(msg)
            timeline_raw.append(result)

        # Convert to TimelineItem objects
        timeline_items: List[TimelineItem] = [
            TimelineItem(**item) for item in timeline_raw
        ]

        # Generate summary
        summary_text = generate_summary(timeline_items)
        trend_text = generate_emotional_trend(timeline_items)
        
        emotion_distribution = Counter(item.emotion for item in timeline_items)
        emotion_distribution = dict(emotion_distribution)


    except Exception as e:
        print(f"❌ Unexpected error during analysis: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during emotion analysis."
        )

    end_time = time.perf_counter()
    processing_time_ms = round((end_time - start_time) * 1000, 2)

    response = AnalyzeResponse(
    timeline=timeline_items,
    summary=summary_text,
    emotional_trend=trend_text,          # ⭐ NEW FIELD
    processing_time_ms=processing_time_ms,
    emotion_distribution=emotion_distribution   # ⭐ NEW FIELD
)


    return response


# -----------------------------
# To run:
# uvicorn main:app --reload
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
