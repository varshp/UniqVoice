#!/usr/bin/env python3
"""
scripts/run_onboarding.py
-------------------------
Role: Standalone CLI to trigger the M6 Voice Onboarding pipeline.

Usage:
  uv run python scripts/run_onboarding.py path/to/clip.mp3 "Answer 1" "Answer 2" "Answer 3"
"""

import argparse
import logging
import sys

from dotenv import load_dotenv

# Load env before importing anything else
load_dotenv()

from agents.onboarding.voice_profile_builder import build_voice_profile

logging.basicConfig(level=logging.INFO, format="%(message)s")

def main():
    parser = argparse.ArgumentParser(description="Run the Voice-Aware Onboarding flow.")
    parser.add_argument("audio_path", help="Path to the 1-minute audio clip.")
    parser.add_argument("answers", nargs="*", help="Optional text answers from the user.")
    args = parser.parse_args()

    logging.info("Starting voice profile extraction...")
    success = build_voice_profile(args.audio_path, args.answers)
    
    if success:
        logging.info("Onboarding complete! You can now start the ADK playground.")
    else:
        logging.error("Onboarding failed. Please check the logs.")
        sys.exit(1)

if __name__ == "__main__":
    main()
