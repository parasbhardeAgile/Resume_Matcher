# File: apps/backend/app/services/resume_service.py

import os
import uuid
import json
import tempfile
import logging

from markitdown import MarkItDown
# Removed SQLAlchemy imports
from pydantic import ValidationError
from typing import Dict, Optional, Tuple

# Removed Model imports
from app.agent import AgentManager
from app.prompt import prompt_factory
from app.schemas.json import json_schema_factory
from app.schemas.pydantic import StructuredResumeModel
from .exceptions import ResumeValidationError # Keep validation error
from json_repair import repair_json
logger = logging.getLogger(__name__)


class ResumeService:
    # Removed db: AsyncSession dependency
    def __init__(self):
        # Removed self.db assignment
        self.md = MarkItDown(enable_plugins=False)
        self.json_agent_manager = AgentManager() # Keep AgentManager

        # Validate dependencies for DOCX processing (optional, can be kept)
        self._validate_docx_dependencies()

    def _validate_docx_dependencies(self):
        # --- This method remains the same ---
        missing_deps = []
        try:
            from markitdown.converters import DocxConverter
            DocxConverter()
        except ImportError:
            missing_deps.append("markitdown[all]==0.1.2")
        except Exception as e:
            if "MissingDependencyException" in str(e) or "dependencies needed to read .docx files" in str(e):
                missing_deps.append("markitdown[all]==0.1.2 (current installation missing DOCX extras)")

        if missing_deps:
            logger.warning(
                f"Missing dependencies for DOCX processing: {', '.join(missing_deps)}. "
                f"DOCX file processing may fail. Install with: pip install {' '.join(missing_deps)}"
            )

    # Renamed method, removed db storage, changed return type
    async def parse_resume(
        self, file_bytes: bytes, file_type: str, filename: str
    ) -> Tuple[str, Dict | None]:
        """
        Converts resume file (PDF/DOCX) to text using MarkItDown and
        extracts structured JSON data using an LLM. Does NOT store in DB.

        Args:
            file_bytes: Raw bytes of the uploaded file
            file_type: MIME type of the file
            filename: Original filename

        Returns:
            A tuple containing:
            - str: The extracted text content of the resume.
            - Dict | None: The extracted structured data as a dictionary, or None if extraction fails.

        Raises:
            ResumeValidationError: If structured data extraction fails validation.
            Exception: If file conversion fails.
        """
        text_content = ""
        structured_resume_data = None
        temp_path = None

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=self._get_file_extension(file_type)
        ) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        try:
            # --- File Conversion ---
            try:
                logger.info(f"Converting file: {filename} ({file_type})")
                result = self.md.convert(temp_path)
                text_content = result.text_content
                if not text_content or not text_content.strip():
                     logger.warning(f"Conversion resulted in empty text content for file: {filename}")
                     # Raise error for empty content before trying LLM
                     raise ResumeValidationError(message="Resume file appears to be empty or could not be read.")
                logger.info(f"Successfully converted file to text content (length: {len(text_content)})")

            except Exception as e:
                # Handle specific markitdown conversion errors (keep this section)
                error_msg = str(e)
                logger.error(f"MarkItDown conversion failed for {filename}: {error_msg}", exc_info=True)
                if "MissingDependencyException" in error_msg or "DocxConverter" in error_msg:
                    raise Exception(...) # Keep specific error messages
                elif "docx" in error_msg.lower():
                    raise Exception(...) # Keep specific error messages
                else:
                    raise Exception(f"File conversion failed: {error_msg}") from e

            # --- Structured Data Extraction ---
            logger.info(f"Attempting structured data extraction for file: {filename}")
            logger.info(f"text_content: " + text_content)
            structured_resume_data = await self._extract_structured_json(text_content)
            # _extract_structured_json raises ResumeValidationError on failure

            if structured_resume_data:
                 logger.info(f"Successfully extracted structured data for file: {filename}")
            else:
                 # This case should ideally be covered by exception in _extract_structured_json
                 logger.error(f"Structured data extraction returned None unexpectedly for file: {filename}")
                 raise ResumeValidationError(message="Failed to extract structured data from resume.")

            # Return the results instead of storing
            return text_content, structured_resume_data

        finally:
            # Ensure temporary file is always cleaned up (keep this section)
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.debug(f"Removed temporary file: {temp_path}")
                except OSError as e:
                    logger.error(f"Error removing temporary file {temp_path}: {e}")

    def _get_file_extension(self, file_type: str) -> str:
        """Returns the appropriate file extension based on MIME type"""
        # --- This method remains the same ---
        if file_type == "application/pdf":
            return ".pdf"
        elif (
            file_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):
            return ".docx"
        return ""

    # Removed _store_resume_in_db method
    # Removed _extract_and_store_structured_resume method

    async def _extract_structured_json(self, resume_text: str) -> Dict | None:
        if not resume_text or not resume_text.strip():
            logger.warning("Cannot extract structured JSON from empty resume text.")
            raise ResumeValidationError(message="Cannot parse structure from empty resume content.")
    
        prompt_template = prompt_factory.get("structured_resume")
        prompt = prompt_template.format(
            json.dumps(json_schema_factory.get("structured_resume"), indent=2),
            resume_text,
        )
        logger.debug("Sending prompt for structured resume extraction.")
    
        generation_config = {
            "max_tokens": 8192,
            "max_output_tokens": 8192,
            "num_predict": 8192
        }
    
        try:
            raw_output = await self.json_agent_manager.run(
                prompt=prompt,
                **generation_config
            )
            logger.info(f"raw_output: {raw_output}")
        except Exception as agent_error:
            logger.error(f"AgentManager failed during structured JSON extraction: {agent_error}", exc_info=True)
            raise ResumeValidationError(message=f"AI agent failed to process the resume content: {agent_error}")
    
        # --- Step 1: Detect Gemini truncation or incomplete JSON ---
        if isinstance(raw_output, dict) and raw_output.get("_finish_reason") == "MAX_TOKENS":
            logger.warning("Gemini output truncated at MAX_TOKENS; attempting continuation.")
            continuation_prompt = "Continue from where you left off. Finish the remaining JSON exactly."
            try:
                continuation_output = await self.json_agent_manager.run(
                    prompt=continuation_prompt,
                    **generation_config
                )
                raw_output = (raw_output.get("text") or "") + (continuation_output or "")
            except Exception as continuation_error:
                logger.error(f"Continuation failed: {continuation_error}", exc_info=True)
    
        # --- Step 2: Attempt to parse or repair JSON ---
        parsed = None
        if isinstance(raw_output, str):
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError:
                logger.warning("Malformed JSON detected; attempting json_repair.")
                try:
                    repaired = repair_json(raw_output)
                    parsed = json.loads(repaired)
                except Exception as repair_error:
                    logger.error(f"JSON repair failed: {repair_error}", exc_info=True)
                    raise ResumeValidationError(message="Resume extraction failed due to truncated JSON output.")
    
        elif isinstance(raw_output, dict):
            parsed = raw_output
        else:
            raise ResumeValidationError(message="Unexpected output format from AI agent.")
    
        # --- Step 3: Validate with Pydantic ---
        try:
            structured_resume_model = StructuredResumeModel.model_validate(parsed)
            return structured_resume_model.model_dump()
        except ValidationError as e:
            logger.error(f"Validation error: {e.errors()}", exc_info=True)
            details = "; ".join([f"{' -> '.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()])
            raise ResumeValidationError(message=f"Resume structure validation failed: {details}")
    
        # Removed get_resume_with_processed_data method