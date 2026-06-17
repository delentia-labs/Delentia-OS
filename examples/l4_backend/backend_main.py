# backend_main.py - FastAPI Server for running quantized SLM on Nvidia L4 GPU
import os
import torch
import logging
import uuid
import time
from fastapi import FastAPI, HTTPException, Security, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("L4-Backend")

app = FastAPI(
    title="Delentia OS - Real Model Backend Engine (Nvidia L4)",
    description="Dedicated FastAPI server running on Nvidia L4 with Quantized LLM, dynamic PEFT adapter merging, and OpenAI-compatible API.",
    version="1.0.0"
)

# Configuration from Environment Variables
BASE_MODEL = os.getenv("RCT_BASE_MODEL", "unsloth/llama-3-8b-Instruct-bnb-4bit")
ADAPTER_MODEL = os.getenv("RCT_ADAPTER_MODEL", "Delentia/delentia-guardian-adapter-v1.3")

# Globals to hold model and tokenizer
model = None
tokenizer = None

async def get_brain_key(request: Request) -> str:
    expected_key = os.getenv("RCT_CORE_BRAIN_KEY", "default_secret_key")
    
    # 1. Try X-RCT-Brain-Key header
    key = request.headers.get("X-RCT-Brain-Key")
    
    # 2. Fallback to Authorization Bearer header
    if not key:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            key = auth_header[7:]
            
    if key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid brain key authorization")
    return key

@app.on_event("startup")
def load_model():
    global model, tokenizer
    logger.info("Initializing Nvidia L4 Model Backend Loader...")
    
    try:
        logger.info(f"Loading base tokenizer from: {BASE_MODEL}")
        tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
        
        logger.info(f"Loading quantized base model on CUDA: {BASE_MODEL}")
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            device_map="auto",
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True
        )
        
        hf_token = os.getenv("HF_TOKEN")
        if hf_token:
            logger.info(f"Connecting to Hugging Face Hub to retrieve PEFT Adapter: {ADAPTER_MODEL}")
            # Load adapter
            model = PeftModel.from_pretrained(model, ADAPTER_MODEL, use_auth_token=hf_token)
            # Merge weights for optimized inference latency
            logger.info("Merging PEFT Adapter weights into base model...")
            model = model.merge_and_unload()
            logger.info("✅ Adapter merged successfully.")
        else:
            logger.warning("⚠️ No HF_TOKEN environment variable found. Running un-adapted base model.")
            
        logger.info("🔥 Backend Model engine is fully loaded and ready on CUDA device.")
        
    except Exception as e:
        logger.critical(f"❌ Failed to load model backend: {e}")
        raise e

# --- Legacy /v1/generate Endpoint ---
class GenerateRequest(BaseModel):
    prompt: str
    temperature: float = 0.2
    max_tokens: int = 512
    top_p: float = 0.9

@app.post("/v1/generate")
async def generate(request: GenerateRequest, brain_key: str = Depends(get_brain_key)):
    global model, tokenizer
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model is still loading, please retry shortly.")
        
    try:
        inputs = tokenizer(request.prompt, return_tensors="pt").to("cuda")
        logger.info("Running token generation on Nvidia L4 GPU...")
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                do_sample=request.temperature > 0.0
            )
            
        generated_tokens = outputs[0][inputs.input_ids.shape[1]:]
        response_text = tokenizer.decode(generated_tokens, skip_special_tokens=True)
        
        return {
            "response": response_text.strip(),
            "model": ADAPTER_MODEL if os.getenv("HF_TOKEN") else BASE_MODEL,
            "device": str(model.device)
        }
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- OpenAI-Compatible Chat Completions Endpoint ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = 512
    top_p: Optional[float] = 0.9

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, brain_key: str = Depends(get_brain_key)):
    global model, tokenizer
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model is still loading, please retry shortly.")
        
    try:
        # Build prompt from messages
        prompt = ""
        for msg in request.messages:
            prompt += f"[{msg.role.upper()}]: {msg.content}\n"
        prompt += "[ASSISTANT]:"
        
        inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
        prompt_tokens_len = inputs.input_ids.shape[1]
        
        logger.info("Running OpenAI-compatible completions on Nvidia L4 GPU...")
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                do_sample=request.temperature > 0.0
            )
            
        generated_tokens = outputs[0][prompt_tokens_len:]
        completion_tokens_len = len(generated_tokens)
        response_text = tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
        
        # Standard OpenAI response format
        return {
            "id": f"chatcmpl-{str(uuid.uuid4())[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model or ADAPTER_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens_len,
                "completion_tokens": completion_tokens_len,
                "total_tokens": prompt_tokens_len + completion_tokens_len
            }
        }
        
    except Exception as e:
        logger.error(f"Chat completions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    }
