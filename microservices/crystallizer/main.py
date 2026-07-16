# main.py - FastAPI wrapper for Crystallizer Engine
import sys
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Setup path to import crystallizer and core packages
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from crystallizer import Crystallizer  # noqa: E402

app = FastAPI(title="Delentia OS - Crystallizer Engine")
engine = Crystallizer()

class CrystallizeRequest(BaseModel):
    text: str

@app.post("/crystallize")
async def crystallize_text(req: CrystallizeRequest):
    try:
        concept_maps = await engine.crystallize(req.text)
        return [cmap.to_dict() for cmap in concept_maps]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/stats")
async def stats():
    return engine.get_statistics()
