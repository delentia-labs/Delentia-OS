"""
Tier Router - เลือก Tier ที่เหมาะสมสำหรับการวิเคราะห์
Stage 2 ของ SignedAI Pipeline
"""

import logging
from typing import Any, Dict

from .models import (
    AnalysisJob,
    RiskLevel,
    TierLevel,
)

logger = logging.getLogger(__name__)


class TierRouter:
    """
    Tier Router สำหรับเลือก Tier ที่เหมาะสม
    
    กลยุทธ์การเลือก Tier:
    1. ตรวจสอบ manual override (ถ้ามี)
    2. คำนวณ risk level จาก artifact
    3. เลือก tier ตาม routing rules
    4. ปรับให้เหมาะสมกับ budget constraints
    """
    
    def __init__(self):
        self.routing_rules = self._load_routing_rules()
        logger.info("TierRouter initialized")
    
    def route(self, job: AnalysisJob) -> AnalysisJob:
        """
        กำหนด Tier สำหรับ job
        
        Args:
            job: AnalysisJob ที่ต้องการกำหนด tier
            
        Returns:
            AnalysisJob พร้อม risk_level และ tier ที่กำหนดแล้ว
        """
        logger.info(f"Routing job {job.id}")
        
        # 1. Check manual override
        if not job.tier_auto_selected:
            logger.info(f"Manual tier override: {job.tier}")
            return job
        
        # 2. Calculate risk level
        if not job.risk_level:
            job.risk_level = self._calculate_risk_level(job)
        
        # 3. Select tier based on risk
        job.tier = self._select_tier(job)
        
        logger.info(f"Job {job.id} routed to {job.tier} (risk: {job.risk_level})")
        return job
    
    def _calculate_risk_level(self, job: AnalysisJob) -> RiskLevel:
        """
        คำนวณระดับความเสี่ยง
        
        ปัจจัยที่พิจารณา:
        - ประเภทของ artifact
        - คำใน intent
        - patterns ที่พบใน content
        - tags ที่ระบุ
        """
        risk_score = 0
        
        # 1. Check artifact type
        if job.artifact_type in ["config", "schema"]:
            risk_score += 1
        
        # 2. Check intent for critical keywords (check all JITNA fields)
        intent_parts = [
            getattr(job.intent, "I", "") or "",
            getattr(job.intent, "D", "") or "",
            getattr(job.intent, "delta", "") or "",
            getattr(job.intent, "R", "") or ""
        ]
        intent_text = " ".join(intent_parts).lower()
        
        critical_keywords = ["security", "auth", "authentication", "password", "token", "secret", "vulnerability", "vulnerabilities"]
        high_keywords = ["database", "migration", "encryption", "permission", "data loss"]
        medium_keywords = ["api", "implementation", "endpoint"]
        production_keywords = ["production", "deploy"]
        
        keyword_score = 0
        critical_match = False
        high_match = False
        
        for keyword in critical_keywords:
            if keyword in intent_text:
                critical_match = True
                break
        
        for keyword in high_keywords:
            if keyword in intent_text:
                high_match = True
        
        medium_count = sum(1 for keyword in medium_keywords if keyword in intent_text)
        
        if critical_match:
            keyword_score = 4
        elif high_match:
            keyword_score = 3
        elif medium_count >= 2:
            keyword_score = 2
        elif medium_count == 1:
            keyword_score = 1
        
        for keyword in production_keywords:
            if keyword in intent_text:
                keyword_score += 1
                break
        
        risk_score += keyword_score
        
        # 3. Check tags
        if job.tags.get("environment") == "production":
            risk_score += 3
        elif job.tags.get("environment") == "staging":
            risk_score += 1
        
        if job.tags.get("criticality") == "high":
            risk_score += 2
        
        # Map score to risk level
        if risk_score >= 4:
            return RiskLevel.CRITICAL
        elif risk_score >= 3:
            return RiskLevel.HIGH
        elif risk_score >= 1:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _select_tier(self, job: AnalysisJob) -> TierLevel:
        """
        เลือก Tier ตาม risk level
        """
        if job.risk_level is None:
            return TierLevel.TIER_S
        risk_to_tier: Dict[RiskLevel, TierLevel] = {
            RiskLevel.LOW: TierLevel.TIER_S,
            RiskLevel.MEDIUM: TierLevel.TIER_4,
            RiskLevel.HIGH: TierLevel.TIER_6,
            RiskLevel.CRITICAL: TierLevel.TIER_8,
        }
        return risk_to_tier.get(job.risk_level, TierLevel.TIER_S)
    
    def _load_routing_rules(self) -> Dict[str, Any]:
        """
        โหลด routing rules
        """
        return {
            "patterns": {
                "**/*.test.ts": {"risk": RiskLevel.LOW, "tier": TierLevel.TIER_S},
                "src/api/**": {"risk": RiskLevel.MEDIUM, "tier": TierLevel.TIER_4},
                "**/auth/**": {"risk": RiskLevel.CRITICAL, "tier": TierLevel.TIER_8},
                "**/security/**": {"risk": RiskLevel.CRITICAL, "tier": TierLevel.TIER_8},
            },
            "keywords": {
                "security": RiskLevel.CRITICAL,
                "production": RiskLevel.HIGH,
                "api": RiskLevel.MEDIUM,
                "test": RiskLevel.LOW,
            }
        }
    
    def estimate_cost(self, tier: TierLevel) -> float:
        """
        ประเมินต้นทุนต่อ query ตาม tier (USD)
        """
        cost_map = {
            TierLevel.TIER_S: 0.03,
            TierLevel.TIER_4: 0.12,
            TierLevel.TIER_6: 0.20,
            TierLevel.TIER_8: 0.30,
        }
        return cost_map.get(tier, 0.03)
    
    def estimate_duration(self, tier: TierLevel) -> int:
        """
        ประเมินเวลาในการวิเคราะห์ (milliseconds)
        """
        duration_map = {
            TierLevel.TIER_S: 1500,
            TierLevel.TIER_4: 5000,
            TierLevel.TIER_6: 10000,
            TierLevel.TIER_8: 15000,
        }
        return duration_map.get(tier, 1500)


__all__ = ["TierRouter"]
