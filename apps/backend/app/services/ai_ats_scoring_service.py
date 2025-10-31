# In: apps/backend/app/services/ai_ats_scoring_service.py
import logging
import json
from typing import Dict, Any
from app.agent import AgentManager
from app.prompt import prompt_factory
from json_repair import repair_json  # Good for safety

logger = logging.getLogger(__name__)

class AiAtsScoringService:
    """
    Calls the Gemini AI provider to generate an ATS score and suggestions
    based on structured resume data.
    """
    def __init__(self):
        logger.info("AI ATS Scoring Service initialized")
        # Instantiate the AgentManager to use the JSON strategy.
        # This will automatically use your configured Gemini provider
        # and the JSONWrapper strategy.
        self.json_agent_manager = AgentManager(strategy="json")

    async def get_ai_ats_score(self, processed_resume_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates an AI-powered ATS score and report.
        """
        resume_id = processed_resume_data.get("Personal Data", {}).get("email", "unknown_resume")
        logger.info(f"Generating AI ATS score for: {resume_id}")

        try:
            # 1. Get the new prompt template
            prompt_template = prompt_factory.get("ai_ats_score")

            # 2. Format the prompt with the resume data
            resume_data_json = json.dumps(processed_resume_data, indent=2)
            logger.info(f"Resume data JSON: {resume_data_json}")
            prompt = prompt_template.format(processed_resume_data_json=resume_data_json)

            # 3. Call Gemini via the AgentManager
            logger.debug("Sending prompt to AI for scoring...")
            # Set high max tokens, as this JSON response can be large
            raw_output = await self.json_agent_manager.run(
                prompt=prompt,
                max_tokens=8192,
                max_output_tokens=8192,
                num_predict=8192  # for ollama
            )
            logger.debug("Received raw output from AI.")

            # 4. The JSONWrapper (default for AgentManager) should return a dict.
            # We add a fallback just in case.
            if isinstance(raw_output, dict):
                logger.info("AI response parsed as dict successfully.")
                return raw_output

            # Fallback: If output is a string, try to repair and parse it
            logger.warning("AI output was not a dict,attempting json_repair...")
            repaired_json_string = repair_json(str(raw_output))
            parsed_json = json.loads(repaired_json_string)

            logger.info("AI response repaired and parsed successfully.")
            return parsed_json

        except Exception as e:
            logger.error(f"Error during AI score generation for {resume_id}: {e}",
                         exc_info=True)
            # Return a valid error structure
            return {
                "ats_score": 0,
                "error": f"Failed to generate AI score: {str(e)}",
                "score_breakdown_for_sidebar": {},
                "report_details": []
            }