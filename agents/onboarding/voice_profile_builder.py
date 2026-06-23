"""
agents/onboarding/voice_profile_builder.py
------------------------------------------
Role: Run-once onboarding agent. Reads an audio file and text answers,
      extracts the user's voice profile, and saves it to a JSON file.

Governed by: specs/SPEC.md Section 11.1.
Milestone:   M6
"""

import json
import logging
import os
from typing import Optional, List

from google.genai import Client, types

logger = logging.getLogger(__name__)

_PROFILE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "profile"
)
_PROFILE_PATH = os.path.join(_PROFILE_DIR, "voice_profile.json")

# The user requested gemini-3.5-flash for onboarding async analysis
_MODEL = os.getenv("ONBOARDING_MODEL", "gemini-3.5-flash")

def build_voice_profile(audio_path: str, text_answers: List[str]) -> bool:
    """
    Extracts voice profile from audio + text and persists to JSON.
    Returns True on success, False if the audio is invalid/too short.
    """
    if not os.path.exists(audio_path):
        logger.error("[VoiceBuilder] Audio file not found at %s", audio_path)
        return False

    client = Client()

    # Read the audio file into bytes
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
        
    ext = os.path.splitext(audio_path)[1].lower()
    mime_type = "audio/mp3"
    if ext in [".m4a", ".mp4"]:
        mime_type = "audio/mp4"
    elif ext in [".wav"]:
        mime_type = "audio/wav"
        
    audio_part = types.Part.from_bytes(
        data=audio_bytes,
        mime_type=mime_type
    )

    answers_block = ""
    if text_answers:
        answers_block = f"\nOptional user text answers (use as refinements):\n{json.dumps(text_answers, indent=2)}\n"

    prompt = f"""
    You are an expert ghostwriter and linguist. Analyse the provided 1-minute audio clip.
    The user is talking naturally about what they write and how they write.
    {answers_block}
    Your task:
    Derive the user's voice profile ENTIRELY from the audio clip. Analyze their tone, 
    sentence rhythm, signature vocabulary, rhetorical patterns, and what they avoid. 
    Also extract the topics they care about directly from what they say in the audio.
    If text answers are provided above, treat them as optional refinements layered on top.

    CRITICAL EDGE CASE: If the audio clip is less than 20 seconds long, or does not 
    contain human speech, DO NOT fabricate a profile. Instead, output exactly:
    ERROR: CLIP_TOO_SHORT

    Otherwise, output ONLY a JSON object matching this schema exactly:
    {{
      "voice_profile": {{
        "tone": "<e.g., direct, warm, slightly contrarian>",
        "sentence_rhythm": "<e.g., short punchy openers, longer middles>",
        "vocabulary": ["<signature word 1>", "<signature word 2>"],
        "rhetorical_moves": ["<e.g., opens with a stat, ends with a challenge>"],
        "avoid": ["<e.g., clichés, words they never use>"]
      }},
      "tone_notes": "<free-text summary of the voice for the drafter prompt>",
      "topic_seeds": ["<broad topic lane 1>", "<broad topic lane 2>"]
    }}
    
    Output ONLY the JSON object. No preamble, no markdown formatting.
    """

    logger.info("[VoiceBuilder] Sending multimodal request to %s...", _MODEL)
    try:
        resp = client.models.generate_content(
            model=_MODEL,
            contents=[audio_part, prompt]
        )
        result = resp.text.strip() if resp.text else ""
        
        if "ERROR: CLIP_TOO_SHORT" in result:
            logger.error("[VoiceBuilder] The audio clip is too short or missing speech. Please re-record.")
            return False
            
        # Clean up possible markdown fences
        if result.startswith("```json"):
            result = result[7:-3]
        elif result.startswith("```"):
            result = result[3:-3]
            
        data = json.loads(result.strip())
        
        # Save to profile directory
        os.makedirs(_PROFILE_DIR, exist_ok=True)
        with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        logger.info("[VoiceBuilder] Voice profile successfully saved to %s", _PROFILE_PATH)
        return True

    except json.JSONDecodeError as e:
        logger.error("[VoiceBuilder] Failed to parse JSON response: %s", e)
        logger.debug("[VoiceBuilder] Raw response: %s", result)
        return False
    except Exception as e:
        logger.error("[VoiceBuilder] Failed to generate profile: %s", e)
        return False
