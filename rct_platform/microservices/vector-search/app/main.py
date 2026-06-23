"""
Main FastAPI Application - ALGO-16 Vector Search
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from contextlib import asynccontextmanager

from .api import routes
from .core.vector_engine import VectorEngine
from .backends.faiss_backend import FAISSBackend
from .backends.qdrant_backend import QdrantBackend
from .models.schemas import ServiceInfo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global engine
engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown
    """
    # Startup
    logger.info("🚀 Starting ALGO-16 Vector Search Service...")
    
    global engine
    
    # Get configuration from environment
    backend_type = os.getenv("BACKEND", "faiss").lower()
    dimension = int(os.getenv("DIMENSION", "768"))
    
    # Initialize backend
    if backend_type == "faiss":
        index_type = os.getenv("FAISS_INDEX_TYPE", "flat")
        metric = os.getenv("FAISS_METRIC", "cosine")
        nlist = int(os.getenv("FAISS_NLIST", "100"))
        m = int(os.getenv("FAISS_M", "32"))
        
        backend = FAISSBackend(
            index_type=index_type,
            metric=metric,
            nlist=nlist,
            m=m
        )
        logger.info(f"Using FAISS backend: type={index_type}, metric={metric}")
    
    elif backend_type == "qdrant":
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        collection = os.getenv("QDRANT_COLLECTION", "vectors")
        metric = os.getenv("QDRANT_DISTANCE", "cosine")
        
        backend = QdrantBackend(
            url=qdrant_url,
            collection_name=collection,
            metric=metric
        )
        logger.info(f"Using Qdrant backend: url={qdrant_url}, collection={collection}")
    
    else:
        raise ValueError(f"Unknown backend: {backend_type}")
    
    # Initialize backend
    backend.initialize(dimension)
    
    # Create engine
    engine = VectorEngine(backend, dimension)
    routes.set_vector_engine(engine)
    
    logger.info(f"✅ Vector Search Service ready on port 8016")
    logger.info(f"   Backend: {backend_type}")
    logger.info(f"   Dimension: {dimension}")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Vector Search Service...")


# Create FastAPI app
app = FastAPI(
    title="ALGO-16: Vector Search Service",
    description="High-performance vector search with FAISS and Qdrant backends",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=ServiceInfo)
async def root():
    """
    Get service information
    """
    backend_type = os.getenv("BACKEND", "faiss")
    dimension = int(os.getenv("DIMENSION", "768"))
    
    return ServiceInfo(
        service="Vector Search Service",
        version="1.0.0",
        algorithm="ALGO-16",
        phase="Phase 3",
        backend=backend_type,
        dimension=dimension
    )


# Include routers
app.include_router(routes.router)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler
    """
    logger.error(f"Unhandled exception: {exc}")
    return {
        "error": "Internal server error",
        "detail": str(exc)
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8016,
        reload=False
    )
