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
)
from app.schemas.pydantic import ResumeImprovementRequest

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
    Accepts a PDF or DOCX file (max 2MB), converts it to HTML/Markdown, and stores it in the database.

    Raises:
        HTTPException: If the file type is not supported, file is empty, or file exceeds 2MB limit.
    """
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
    Scores and improves a resume against a job description.

    Raises:
        HTTPException: If the resume or job is not found.
    """
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
    Retrieves resume data from both resume_model and processed_resume model by resume_id.

    Args:
        resume_id: The ID of the resume to retrieve

    Returns:
        Combined data from both resume and processed_resume models

    Raises:
        HTTPException: If the resume is not found or if there's an error fetching data.
    """
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
    
@resume_router.post(
    "/upload-and-score-ats", # New, specific path
    summary="Upload resume, parse, calculate ATS score, return score immediately (DB-less).",
    tags=["ATS Scoring"] # Optional: Add a tag for better OpenAPI docs grouping
)
async def upload_and_score_ats( # New function name
    request: Request,
    file: UploadFile = File(...),
    # db: AsyncSession = Depends(get_db_session), # NO database dependency here
):
    """
    Accepts PDF/DOCX (max 2MB), converts to text, extracts structured data,
    calculates an ATS score based on structure/content, and returns the score immediately.
    Does NOT store data in the database.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.info(f"[{request_id}] Received request for ATS scoring: {file.filename}")

    # --- File Validation Logic (Keep as before) ---
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
        # 1. Parse the resume (using the DB-less ResumeService)
        # Instantiate ResumeService without db
        resume_service = ResumeService()
        logger.info(f"[{request_id}] Parsing resume: {file.filename}")
        # Call the refactored parse_resume method
        text_content, structured_data = await resume_service.parse_resume(
            file_bytes=file_bytes,
            file_type=file.content_type,
            filename=file.filename,
        )
        # Check if structured_data is None (though parse_resume should raise error)
        if structured_data is None:
             logger.error(f"[{request_id}] Parsing returned None for structured_data unexpectedly.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to parse resume structure.")
        logger.info(f"[{request_id}] Resume parsed successfully.")

        # 2. Calculate ATS Score (using the DB-less AtsScoringService)
        # Instantiate AtsScoringService without db
        ats_scoring_service = AtsScoringService()
        # Generate a temporary ID or use filename for context in response
        temp_resume_id = f"upload_{file.filename}_{uuid.uuid4()}"
        logger.info(f"[{request_id}] Calculating ATS score for {temp_resume_id}")
        ats_result = ats_scoring_service.calculate_ats_score(
            resume_id=temp_resume_id, # Pass a reference ID
            processed_resume_data=structured_data # Pass the dictionary directly
        )
        logger.info(f"[{request_id}] ATS score calculated: {ats_result.get('ats_score')}")

        # 3. Return the ATS score result directly
        return JSONResponse(
            content={
                "message": f"File {file.filename} processed and ATS score calculated.",
                "request_id": request_id,
                "ats_score_result": ats_result,
                # Optionally add parsed_data if needed by frontend, but can be large
                # "parsed_data": structured_data
            },
            status_code=status.HTTP_200_OK
        )

    # --- Exception Handling (Keep similar, adjust details) ---
    except ResumeValidationError as e:
        logger.warning(f"[{request_id}] Resume parsing/validation failed for {file.filename}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e), # The error from the service is already user-friendly
        )
    except Exception as e:
        logger.error(
            f"[{request_id}] Error processing file {file.filename}: {str(e)} - traceback: {traceback.format_exc()}"
        )
        # Check if it's a file conversion error we added custom messages for
        if "File conversion failed" in str(e) or "DOCX file processing failed" in str(e):
             detail_msg = str(e) # Use the specific conversion error
        else:
             detail_msg = f"An unexpected error occurred while processing the resume. Please try again."

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail_msg,
        )
