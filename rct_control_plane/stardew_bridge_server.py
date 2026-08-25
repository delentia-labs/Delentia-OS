"""
Delentia OS — Stardew Valley Living World WebSocket Server & NPC Mind Engine
Handles real-time game telemetry, NPC Delta Memory state, and autonomous farm directives.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

from rct_control_plane.algorithm_kernel_41 import ALGORITHM_KERNEL
from rct_control_plane.thai_normalizer import normalize_thai_text


class StardewLivingWorldEngine:
    """Orchestrates Living World NPCs, Farm Swarms, and In-Game Economics."""

    def __init__(self):
        self.npc_memories: Dict[str, Dict[str, Any]] = {
            "Pierre": {
                "affinity": 0.5,
                "traits": ["merchant", "hardworking", "ambitious"],
                "last_topic": "seeds_stock",
                "memories": ["Farmer Whale arrived in Pelican Town."]
            },
            "Robin": {
                "affinity": 0.6,
                "traits": ["carpenter", "creative", "friendly"],
                "last_topic": "farm_buildings",
                "memories": ["Helped rebuild farm cabin."]
            },
            "Abigail": {
                "affinity": 0.7,
                "traits": ["adventurous", "mysterious", "gamer"],
                "last_topic": "mines_exploration",
                "memories": ["Interested in quartz and dungeon crawling."]
            },
            "Lewis": {
                "affinity": 0.8,
                "traits": ["mayor", "bureaucratic", "cautious"],
                "last_topic": "village_tax",
                "memories": ["Welcomed new farmer to the valley."]
            }
        }
        self.current_world_state: Dict[str, Any] = {
            "season": "spring",
            "day": 1,
            "year": 1,
            "weather": "sunny",
            "farmer_gold": 500
        }

    async def process_game_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Processes real-time game events from C# SMAPI Mod."""
        event_type = event_data.get("event_type", "")

        if event_type == "DAY_STARTED":
            self.current_world_state.update({
                "day": event_data.get("day", 1),
                "season": event_data.get("season", "spring"),
                "year": event_data.get("year", 1),
                "weather": event_data.get("weather", "sunny"),
                "farmer_gold": event_data.get("gold", 500)
            })
            # Run 41 algorithms day simulation
            ALGORITHM_KERNEL.algo_03_delta_engine(self.current_world_state)
            return {
                "action_type": "HUD_ALERT",
                "message": f"☀️ Delentia: World State Synchronized (Year {self.current_world_state['year']} {self.current_world_state['season'].capitalize()} Day {self.current_world_state['day']})"
            }

        elif event_type == "NPC_CONVERSATION_TRIGGER":
            npc_name = event_data.get("npc_name", "Villager")
            farmer_name = event_data.get("farmer_name", "Farmer")
            friendship = event_data.get("friendship_points", 0)

            npc_info = self.npc_memories.get(npc_name, {
                "affinity": 0.5,
                "traits": ["friendly"],
                "memories": []
            })
            intimacy_level = "สนิทสนม" if friendship >= 1000 else "คนรู้จัก"

            user_prompt = event_data.get("user_prompt", "").strip()

            # Run through 1+4 LoRA Multiplexer & 41 Algorithms
            algo_res = ALGORITHM_KERNEL.process_intent_full_pipeline(f"NPC Interaction: {npc_name} (Level: {intimacy_level})")
            
            # -----------------------------------------------------------------
            # Real AI Generative Persona Inference (Google Gemma / Gemini)
            # -----------------------------------------------------------------
            gemini_key = os.getenv("GOOGLE_API_KEY", "").strip()
            real_ai_dialogue = None

            if gemini_key:
                try:
                    import aiohttp
                    model_name = "gemma-4-26b-a4b-it"
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
                    
                    system_prompt = (
                        f"You are roleplaying as {npc_name} from Stardew Valley in Delentia Living World. "
                        f"Traits: {', '.join(npc_info.get('traits', []))}. Intimacy level with player ({farmer_name}): {intimacy_level}. "
                        f"Memories: {', '.join(npc_info.get('memories', []))}. "
                        f"Respond in Thai naturally, staying in character as {npc_name}, friendly, lively, and immersive. Keep response concise (1-3 sentences)."
                    )
                    prompt_text = f"ผู้เล่น ({farmer_name}) พูดว่า: '{user_prompt}'" if user_prompt else f"ผู้เล่น ({farmer_name}) เดินเข้ามาทักทายคุณ"
                    
                    req_payload = {
                        "contents": [
                            {
                                "parts": [
                                    {"text": f"คำสั่งบทบาท: {system_prompt}\n\nสถานการณ์: {prompt_text}"}
                                ]
                            }
                        ]
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, json=req_payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                            if resp.status == 200:
                                res_json = await resp.json()
                                real_ai_dialogue = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                except Exception as ex:
                    print(f"[WARN] Live NPC AI generation fallback: {ex}")

            if real_ai_dialogue:
                dialogue = real_ai_dialogue
            else:
                # Dynamic LoRA Fallback
                if npc_name == "Pierre":
                    dialogue = f"สวัสดีคุณ {farmer_name}! วันนี้ร้านของฉันมีเมล็ดพันธุ์คุณภาพเยี่ยมพร้อมปุ๋ยสูตรใหม่ สนใจรับไปลองสักชุดไหมครับ? (ความสัมพันธ์: {intimacy_level})"
                elif npc_name == "Robin":
                    dialogue = f"อ้าว {farmer_name}! วันนี้ไม้ในฟาร์มของคุณดูอุดมสมบูรณ์ดีนะ ถ้าอยากต่อเติมโรงนาหรือเล้าไก่ แวะมาบอกฉันได้เสมอเลย!"
                elif npc_name == "Abigail":
                    dialogue = f"เฮ้ {farmer_name}! วันนี้ฟ้าใสดีจัง... ฉันกำลังคิดว่าจะแอบไปเดินเล่นแถวเหมืองร้างสักหน่อย คุณเคยเจอแร่อะไรแปลกๆ ในนั้นบ้างไหม?"
                elif npc_name == "Lewis":
                    dialogue = f"ยินดีที่ได้พบคุณ {farmer_name}! ในฐานะนายกเทศมนตรีเมือง Pelican Town ฉันภูมิใจมากที่เห็นฟาร์มของคุณค่อยๆ เติบโตขึ้นทุกวัน"
                else:
                    dialogue = f"สวัสดีจ้ะ {farmer_name}! ยินดีที่ได้คุยกันในวันที่อากาศสดใสแบบนี้นะ"

            return {
                "action_type": "INJECT_NPC_DIALOGUE",
                "npc_name": npc_name,
                "text": normalize_thai_text(dialogue),
                "fdia_score": algo_res["fdia_score"],
                "live_ai_generated": (real_ai_dialogue is not None)
            }

        return {"action_type": "NOOP"}


STARDEW_ENGINE = StardewLivingWorldEngine()
