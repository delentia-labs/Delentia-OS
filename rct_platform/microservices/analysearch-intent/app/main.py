"""
Analysearch Intent Service
FastAPI Main Application

Combines Analysis + Research + Intent for the RCT Ecosystem.
Features Mirror Mode (PROPOSE → COUNTER → REFINE), Cross-Disciplinary Synthesis,
GIGO Protection, and Keyword Crystallization.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import routes

app = FastAPI(
    title="Analysearch Intent",
    version="v1.0",
    description="""
    **Analysis + Research + Intent Engine for RCT System v13.0**

    ## Features

    - **Mirror Mode**: PROPOSE → COUNTER → REFINE iterative refinement
    - **Cross-Disciplinary Synthesis**: Find connections across domains
    - **Golden Keyword Extraction**: ALGO-41 inspired crystallization
    - **GIGO Protection**: Entropy-based input validation
    - **Intent Conservation**: Preserve original intent throughout pipeline

    ## Modes

    - `quick` — Fast lookup, minimal analysis
    - `standard` — Standard analysis + research
    - `deep` — Deep analysis with Mirror Mode
    - `mirror` — Full Mirror Mode loop
    """,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/analysearch", tags=["analysearch"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Analysearch Intent",
        "version": "v1.0",
        "status": "running",
        "endpoints": {
            "analyze": "POST /analysearch/analyze",
            "validate": "POST /analysearch/validate",
            "crystallize": "POST /analysearch/crystallize",
            "synthesize": "POST /analysearch/synthesize",
            "session": "GET /analysearch/sessions/{id}",
            "stats": "GET /analysearch/stats",
            "health": "GET /analysearch/health"
        }
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "analysearch-intent"}


@app.on_event("startup")
async def startup_event():
    print("=" * 60)
    print("Analysearch Intent Service")
    print("Version: v1.0")
    print("=" * 60)
    print("✅ Engine initialized")
    print("✅ Mirror Mode ready")
    print("✅ GIGO Protection active")
    print("✅ API endpoints ready")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    print("Analysearch Intent - Shutting down...")
