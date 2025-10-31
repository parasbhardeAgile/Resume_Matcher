import logging
import traceback
import uuid
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import (
    APIRouter,
    File,
    UploadFile,
    HTTPException,
    Depends,
    Request,
    status,
    Query,
)
from typing import Dict, Any # ### NEW: Added for type hinting
from pydantic import BaseModel, Field # ### NEW: Added for request body model

from app.core import get_db_session
from app.services import (
    ResumeService,
    ScoreImprovementService,
    ResumeNotFoundError,
    ResumeParsingError,
    ResumeValidationError,
    JobNotFoundError,
    JobParsingError,
    ResumeKeywordExtractionError,
    JobKeywordExtractionError,
    AtsScoringService,
    AiAtsScoringService,
)
from app.schemas.pydantic import ResumeImprovementRequest

class AtsScoreRequest(BaseModel):
    """
    This is the model for API 2 (POST /score).
    The client will send this JSON in the request body.
    """
    resume_id: str = Field(..., description="The unique ID of the resume (from the client's DB)")
    processed_resume_data: Dict[str, Any] = Field(..., description="The structured resume JSON fetched from the client's DB")


resume_router = APIRouter()
logger = logging.getLogger(__name__)


@resume_router.post(
    "/upload",
    summary="Upload a resume in PDF or DOCX format and store it into DB in HTML/Markdown format",
)
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
):
    """
    (This is your original /upload endpoint, left as-is)
    ...
    """
# ... (existing code for /upload) ...
    request_id = getattr(request.state, "request_id", str(uuid4()))

    allowed_content_types = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    if file.content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only PDF and DOCX files are allowed.",
        )

    MAX_FILE_SIZE = 2 * 1024 * 1024
    
    # Try to get size from file object or Content-Length header
    file_size = getattr(file, 'size', None)
    if file_size is None and hasattr(request, 'headers'):
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                file_size = int(content_length)
            except ValueError:
                pass  # Invalid content-length header
    
    if file_size and file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds maximum allowed size of 2.0MB.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file. Please upload a valid file.",
        )

    # Verify size after reading
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds maximum allowed size of 2.0MB.",
        )

    try:
        resume_service = ResumeService(db)
        resume_id = await resume_service.convert_and_store_resume(
            file_bytes=file_bytes,
            file_type=file.content_type,
            filename=file.filename,
            content_type="md",
        )
    except ResumeValidationError as e:
        logger.warning(f"Resume validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            f"Error processing file: {str(e)} - traceback: {traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}",
        )

    return {
        "message": f"File {file.filename} successfully processed as MD and stored in the DB",
        "request_id": request_id,
        "resume_id": resume_id,
    }


@resume_router.post(
    "/improve",
    summary="Score and improve a resume against a job description",
)
async def score_and_improve(
    request: Request,
    payload: ResumeImprovementRequest,
    db: AsyncSession = Depends(get_db_session),
    stream: bool = Query(
        False, description="Enable streaming response using Server-Sent Events"
    ),
):
    """
    (This is your original /improve endpoint, left as-is)
    ...
    """
# ... (existing code for /improve) ...
    request_id = getattr(request.state, "request_id", str(uuid4()))
    headers = {"X-Request-ID": request_id}

    request_payload = payload.model_dump()

    try:
        resume_id = str(request_payload.get("resume_id", ""))
        if not resume_id:
            raise ResumeNotFoundError(
                message="invalid value passed in `resume_id` field, please try again with valid resume_id."
            )
        job_id = str(request_payload.get("job_id", ""))
        if not job_id:
            raise JobNotFoundError(
                message="invalid value passed in `job_id` field, please try again with valid job_id."
            )
        score_improvement_service = ScoreImprovementService(db=db)

        if stream:
            return StreamingResponse(
                content=score_improvement_service.run_and_stream(
                    resume_id=resume_id,
                    job_id=job_id,
                ),
                media_type="text/event-stream",
                headers=headers,
            )
        else:
            improvements = await score_improvement_service.run(
                resume_id=resume_id,
                job_id=job_id,
            )
            return JSONResponse(
                content={
                    "request_id": request_id,
                    "data": improvements,
                },
                headers=headers,
            )
    except ResumeNotFoundError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except JobNotFoundError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except ResumeParsingError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except JobParsingError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except ResumeKeywordExtractionError as e:
        logger.warning(str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except JobKeywordExtractionError as e:
        logger.warning(str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error: {str(e)} - traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="sorry, something went wrong!",
        )


@resume_router.get(
    "",
    summary="Get resume data from both resume and processed_resume models",
)
async def get_resume(
    request: Request,
    resume_id: str = Query(..., description="Resume ID to fetch data for"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    (This is your original /get endpoint, left as-is)
    ...
    """
# ... (existing code for /get) ...
    request_id = getattr(request.state, "request_id", str(uuid4()))
    headers = {"X-Request-ID": request_id}

    try:
        if not resume_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resume_id is required",
            )

        resume_service = ResumeService(db)
        resume_data = await resume_service.get_resume_with_processed_data(
            resume_id=resume_id
        )
        
        if not resume_data:
            raise ResumeNotFoundError(
                message=f"Resume with id {resume_id} not found"
            )

        return JSONResponse(
            content={
                "request_id": request_id,
                "data": resume_data,
            },
            headers=headers,
        )
    
    except ResumeNotFoundError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error fetching resume: {str(e)} - traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching resume data",
        )


# ### NEW: API 1 - Parse Only (Stateless) ###
@resume_router.post(
    "/parse",
    summary="Upload resume, parse, and return structured JSON data.",
    tags=["ATS Microservice"] 
)
async def parse_resume_stateless(
    request: Request,
    file: UploadFile = File(...),
    # NO database dependency here
):
    """
    API 1 (Stateless):
    Accepts PDF/DOCX (max 2MB), parses it in-memory,
    and returns the structured JSON data.
    It does NOT store anything.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.info(f"[{request_id}] Received request for stateless parsing: {file.filename}")

    # --- File Validation Logic (Copied from /upload-and-score-ats) ---
    allowed_content_types = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    if file.content_type not in allowed_content_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type...")

    MAX_FILE_SIZE = 2 * 1024 * 1024
    file_size = getattr(file, 'size', None)
    if file_size and file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds 2.0MB.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds 2.0MB.")
    # --- End File Validation Logic ---

    try:
        # 1. Parse the resume (stateless)
        resume_service = ResumeService() # Instantiate without db
        logger.info(f"[{request_id}] Parsing resume: {file.filename}")
        
        # Call the parse_resume method
        text_content, structured_data = await resume_service.parse_resume(
            file_bytes=file_bytes,
            file_type=file.content_type,
            filename=file.filename,
        )
        
        if structured_data is None:
            logger.error(f"[{request_id}] Parsing returned None for structured_data unexpectedly.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to parse resume structure.")
        logger.info(f"[{request_id}] Resume parsed successfully.")

        # 2. Return ONLY the parsed data
        return JSONResponse(
            content={
                "message": f"File {file.filename} parsed successfully.",
                "request_id": request_id,
                "parsed_data": structured_data # This is what the client will store
            },
            status_code=status.HTTP_200_OK
        )

    # 3. Exception Handling (Copied from /upload-and-score-ats)
    except ResumeValidationError as e:
        logger.warning(f"[{request_id}] Resume parsing/validation failed for {file.filename}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e), 
        )
    except Exception as e:
        logger.error(
            f"[{request_id}] Error processing file {file.filename}: {str(e)} - traceback: {traceback.format_exc()}"
        )
        if "File conversion failed" in str(e) or "DOCX file processing failed" in str(e):
            detail_msg = str(e)
        else:
            detail_msg = f"An unexpected error occurred while processing the resume. Please try again."

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail_msg,
        )


# ### NEW: API 2 - Score Only Manual logic (Stateless) ###
@resume_router.post(
    "/score",
    summary="Calculate ATS score from provided structured resume data.",
    tags=["ATS Microservice"]
)
async def score_resume_from_data_stateless(
    request: Request,
    payload: AtsScoreRequest, # Use the new Pydantic model
):
    """
    API 2 (Stateless):
    - Receives structured resume data *in the request body*.
    - Calculates the ATS score using AtsScoringService.
    - Returns the score.
    - Does NOT store anything.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.info(f"[{request_id}] Requesting ATS score for resume ID: {payload.resume_id}")

    try:
        # 1. Instantiate the stateless AtsScoringService
        ats_scoring_service = AtsScoringService()
        
        logger.info(f"[{request_id}] Calculating ATS score for {payload.resume_id}")
        
        # 2. Calculate the score using the data from the request body
        ats_result = ats_scoring_service.calculate_ats_score(
            resume_id=payload.resume_id, # Pass the ID from the payload
            processed_resume_data=payload.processed_resume_data # Pass the JSON from the payload
        )
        
        logger.info(f"[{request_id}] ATS score calculated: {ats_result.get('ats_score')}")

        # 3. Return the ATS score result
        return JSONResponse(
            content={
                "message": "ATS score calculated successfully from provided data.",
                "request_id": request_id,
                "resume_id": payload.resume_id,
                "ats_score_result": ats_result,
            },
            status_code=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(
            f"[{request_id}] Error scoring resume {payload.resume_id}: {str(e)} - traceback: {traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while calculating the score.",
        )

### NEW: API 2 - Score Only AI logic (Stateless) ###

@resume_router.post(
    "/ai-score",
    summary="Calculate ATS score from provided structured resume data.",
    tags=["ATS Microservice"]
)
async def score_resume_from_data_stateless(
    request: Request,
    payload: AtsScoreRequest, # Use the new Pydantic model
):
    """
    API 2 (Stateless):
    - Receives structured resume data *in the request body*.
    - Calculates the ATS score using AiAtsScoringService.  <-- UPDATED
    - Returns the score.
    - Does NOT store anything.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.info(f"[{request_id}] Requesting AI ATS score for resume ID: {payload.resume_id}")

    try:
        ai_scoring_service = AiAtsScoringService() # <-- UPDATED
        
        logger.info(f"[{request_id}] Calculating AI ATS score for {payload.resume_id}")
        
        ats_result = await ai_scoring_service.get_ai_ats_score( # <-- UPDATED (and added await)
            processed_resume_data=payload.processed_resume_data # Pass the JSON from the payload
        )
        
        logger.info(f"[{request_id}] AI ATS score calculated: {ats_result.get('ats_score')}")

        # 3. Return the ATS score result
        return JSONResponse(
            content={
                "message": "AI ATS score calculated successfully from provided data.",
                "request_id": request_id,
                "resume_id": payload.resume_id,
                "ats_score_result": ats_result,
            },
            status_code=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(
            f"[{request_id}] Error scoring resume {payload.resume_id}: {str(e)} - traceback: {traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while calculating the score.",
        )
