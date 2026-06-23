"""
genome_api.py
Gateway API endpoints for Genome & Creator Profile integration

Provides REST API access to:
- Creator identity (from Architect's Genome v4.0)
- FDIA equation explanation
- Core values (5 values)
- Creator roles (7 roles)
- Complete creator profile

Used by: Frontend Floating Assistant (React widget)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import sys
import os

# Add parent directory to path to import creator_profile_integration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '10_kernel_runtime'))

try:
    from creator_profile_integration import (
        CreatorProfileManager,
        CreatorIdentity,
        FDIAEquation,
        ArchitectValues,
        CreatorRole
    )
except ImportError as e:
    print(f"Warning: Could not import creator_profile_integration: {e}")
    CreatorProfileManager = None

# Create router
router = APIRouter(prefix="/api/genome", tags=["genome"])

# Initialize manager (singleton pattern)
_manager_instance = None

def get_manager() -> CreatorProfileManager:
    """Get or create CreatorProfileManager instance"""
    global _manager_instance
    if _manager_instance is None:
        if CreatorProfileManager is None:
            raise HTTPException(
                status_code=500,
                detail="CreatorProfileManager not available"
            )
        _manager_instance = CreatorProfileManager()
    return _manager_instance


# Response models
class CreatorIdentityResponse(BaseModel):
    """Response model for creator identity"""
    name_th: str
    name_en: str
    birthplace: str
    origin: str
    first_contact_date: str
    turning_point_date: str
    role: str
    story: Dict[str, str]


class FDIAResponse(BaseModel):
    """Response model for FDIA equation"""
    formula: str
    components: Dict[str, Dict[str, str]]
    narrative: Dict[str, str]


class ValueResponse(BaseModel):
    """Response model for a single value"""
    key: str
    name: str
    name_th: str
    description: Dict[str, str]
    constraint: Dict[str, str]


class RoleResponse(BaseModel):
    """Response model for a single role"""
    role: str
    description: str
    icon: str


class CompleteProfileResponse(BaseModel):
    """Complete creator profile response"""
    identity: Dict[str, Any]
    fdia: Dict[str, Any]
    values: List[Dict[str, Any]]
    roles: List[Dict[str, Any]]
    query_type: str
    language: str


# Endpoints

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        manager = get_manager()
        return {
            "status": "healthy",
            "genome_version": "4.0",
            "manager_ready": manager is not None
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e)
        }


@router.get("/creator")
async def get_creator_identity(
    language: str = Query("th", regex="^(th|en)$")
):
    """
    Get complete creator identity
    
    Query params:
    - language: 'th' or 'en' (default: 'th')
    
    Returns:
    - Complete creator profile from Genome v4.0
    """
    try:
        manager = get_manager()
        response = manager.who_is_creator()
        
        lang_data = response.get(language, response.get("th"))
        
        # Build comprehensive response
        identity = manager.identity
        
        return {
            "identity": {
                "name_th": identity.name_th,
                "name_en": identity.name_en,
                "birthplace": identity.birthplace,
                "origin": "8-floor flat community (ชุมชนอพาร์ตเมนต์ 8 ชั้น)",
                "role": "The Architect of the RCT Ecosystem",
                "first_contact": {
                    "date": "2025-06-25",
                    "event": "First Contact with AI",
                    "significance": "Birth of RCT project"
                },
                "turning_point": {
                    "date": "2025-08-11",
                    "event": "Ordination & Father's Passing",
                    "significance": "Major life transformation & commitment"
                }
            },
            "story": lang_data.get("answer", ""),
            "sources": lang_data.get("sources", []),
            "language": language
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching creator identity: {str(e)}")


@router.get("/fdia")
async def get_fdia_equation(
    language: str = Query("th", regex="^(th|en)$")
):
    """
    Get FDIA equation explanation
    
    Query params:
    - language: 'th' or 'en' (default: 'th')
    
    Returns:
    - FDIA formula, components, and narrative explanation
    """
    try:
        manager = get_manager()
        response = manager.get_fdia_explanation(language)
        
        return {
            "formula": response["formula"],
            "components": response["components"],
            "narrative": response["narrative"],
            "language": language
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching FDIA: {str(e)}")


@router.get("/values")
async def get_core_values(
    language: str = Query("th", regex="^(th|en)$")
):
    """
    Get 5 core values
    
    Query params:
    - language: 'th' or 'en' (default: 'th')
    
    Returns:
    - List of 5 core values with descriptions and constraints
    """
    try:
        manager = get_manager()
        values_dict = manager.get_core_values()
        
        # Convert dict to list format with proper field names
        values_list = []
        for key, value_data in values_dict.items():
            values_list.append({
                "key": key,
                "name": value_data.get("en", ""),
                "name_th": value_data.get("thai", ""),
                "description": value_data.get("description", ""),
                "constraint": value_data.get("constraint", "")
            })
        
        return {
            "values": values_list,
            "count": len(values_list),
            "language": language
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching values: {str(e)}")


@router.get("/roles")
async def get_creator_roles():
    """
    Get 7 creator roles in RCT ecosystem
    
    Returns:
    - List of 7 creator roles with descriptions
    """
    try:
        manager = get_manager()
        
        roles = [
            {"role": role.value, "description": "", "icon": ""} 
            for role in CreatorRole
        ]
        
        # Add detailed descriptions
        role_details = {
            "Designer of the Equation": {
                "description": "Created F = (D^I) * A as the foundational philosophy",
                "icon": "🧮"
            },
            "Author of the Codex": {
                "description": "Wrote RCT Codex defining principles and values",
                "icon": "📚"
            },
            "Builder of the Vault": {
                "description": "Built Vault1068 (1000+ file knowledge base)",
                "icon": "🏛️"
            },
            "Orchestrator of AI Agents": {
                "description": "Designed ArtentAI (Creator) & SignedAI (Verifier)",
                "icon": "🎭"
            },
            "Survivor Architect": {
                "description": "Designs with empathy from lived experience",
                "icon": "🛡️"
            },
            "Architect of Intent": {
                "description": "Created JITNA (Language of Intent)",
                "icon": "🧠"
            },
            "Geneticist of Cognition": {
                "description": "Designed Genome system for agent DNA",
                "icon": "🧬"
            }
        }
        
        for role in roles:
            role_name = role["role"]
            if role_name in role_details:
                role["description"] = role_details[role_name]["description"]
                role["icon"] = role_details[role_name]["icon"]
        
        return {
            "roles": roles,
            "count": len(roles)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching roles: {str(e)}")


@router.get("/complete")
async def get_complete_profile(
    language: str = Query("th", regex="^(th|en)$")
):
    """
    Get complete creator profile (all data in one call)
    
    Query params:
    - language: 'th' or 'en' (default: 'th')
    
    Returns:
    - Complete profile: identity + FDIA + values + roles
    """
    try:
        manager = get_manager()
        
        # Get all data
        creator_response = await get_creator_identity(language)
        fdia_response = await get_fdia_equation(language)
        values_response = await get_core_values(language)
        roles_response = await get_creator_roles()
        
        return {
            "identity": creator_response["identity"],
            "story": creator_response["story"],
            "fdia": fdia_response,
            "values": values_response["values"],
            "roles": roles_response["roles"],
            "sources": creator_response.get("sources", []),
            "language": language,
            "genome_version": "4.0"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching complete profile: {str(e)}")


from pydantic import BaseModel

class QueryRequest(BaseModel):
    query: str
    language: str = "th"

@router.post("/query")
async def query_creator(request: QueryRequest):
    """
    Ask a question to the creator profile system
    
    Body:
    - query: Question to ask (required)
    - language: 'th' or 'en' (default: 'th')
    
    Returns:
    - Contextual answer based on Genome data
    """
    try:
        manager = get_manager()
        
        # Route query to appropriate response
        query_lower = request.query.lower()
        
        if any(word in query_lower for word in ["who", "ใคร", "creator", "ผู้สร้าง"]):
            return await get_creator_identity(request.language)
        elif any(word in query_lower for word in ["fdia", "equation", "สมการ", "ปรัชญา"]):
            return await get_fdia_equation(request.language)
        elif any(word in query_lower for word in ["value", "ค่านิยม", "principle"]):
            return await get_core_values(request.language)
        elif any(word in query_lower for word in ["role", "บทบาท", "position"]):
            return await get_creator_roles()
        else:
            # Default: return complete profile
            return await get_complete_profile(request.language)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


# Export router
__all__ = ["router"]
