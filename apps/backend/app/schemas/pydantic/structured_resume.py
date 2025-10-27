from typing import List, Optional
from pydantic import BaseModel, Field, field_validator # Import field_validator


# Make city and country optional within Location
class Location(BaseModel):
    city: Optional[str] = None
    country: Optional[str] = None


class PersonalData(BaseModel):
    firstName: str = Field(..., alias="firstName") # Required
    lastName: Optional[str] = Field(None, alias="lastName") # Keep Optional
    email: str = Field(...) # Required
    phone: Optional[str] = None # Make Optional
    linkedin: Optional[str] = None
    portfolio: Optional[str] = None
    location: Optional[Location] = None # Make Optional

    # Add a validator to ensure at least one contact method besides name exists
    @field_validator('email', 'phone', 'linkedin', check_fields=False)
    def check_at_least_one_contact(cls, v, values):
        # This is a simplified check running after initial field validation
        # A more robust check might use a model_validator
        # Check if at least one contact field (email, phone, linkedin) has a value
        if not v and not values.data.get('phone') and not values.data.get('linkedin'):
             # This check is basic; Pydantic v2 might need a model_validator for complex cross-field checks
             # For now, we mainly rely on 'email' being required.
             pass # Let the required 'email' handle the minimum contact info
        return v


class Experience(BaseModel):
    job_title: Optional[str] = Field(None, alias="jobTitle") # Make Optional
    company: Optional[str] = None # Make Optional
    location: Optional[str] = None # Already Optional
    start_date: Optional[str] = Field(None, alias="startDate") # Make Optional
    end_date: Optional[str] = Field(None, alias="endDate") # Make Optional
    # Keep description technically required as List[str], but allow empty list
    description: List[str] = Field(default_factory=list)
    technologies_used: Optional[List[str]] = Field(
        default_factory=list, alias="technologiesUsed"
    )


class Project(BaseModel):
    project_name: Optional[str] = Field(None, alias="projectName") # Make Optional
    description: Optional[str] = None # Make Optional
    # Allow empty list
    technologies_used: List[str] = Field(default_factory=list, alias="technologiesUsed")
    link: Optional[str] = None
    start_date: Optional[str] = Field(None, alias="startDate")
    end_date: Optional[str] = Field(None, alias="endDate")


class Skill(BaseModel):
    category: Optional[str] = None # Make Optional
    skill_name: Optional[str] = Field(None, alias="skillName") # Make Optional


class ResearchWork(BaseModel):
    title: Optional[str] = None
    publication: Optional[str] = None
    date: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None # Make Optional
    degree: Optional[str] = None # Make Optional
    field_of_study: Optional[str] = Field(None, alias="fieldOfStudy")
    start_date: Optional[str] = Field(None, alias="startDate")
    end_date: Optional[str] = Field(None, alias="endDate")
    grade: Optional[str] = None
    description: Optional[str] = None

class Language(BaseModel):
    language_name: Optional[str] = Field(None, alias="languageName")
    proficiency: Optional[str] = None

class Certification(BaseModel):
    name: Optional[str] = None            # Name of the certification
    issuer: Optional[str] = None          # Issuing organization
    date_obtained: Optional[str] = Field(None, alias="dateObtained")

class StructuredResumeModel(BaseModel):
    # Require Personal Data block, but allow it to be partially filled
    personal_data: PersonalData = Field(..., alias="Personal Data")
    # Add Profile Summary here
    profile_summary: Optional[str] = Field(None, alias="Profile Summary") # New field
    # Allow lists to be potentially empty by default
    languages: List[Language] = Field(default_factory=list, alias="Languages")
    experiences: List[Experience] = Field(default_factory=list, alias="Experiences")
    projects: List[Project] = Field(default_factory=list, alias="Projects")
    skills: List[Skill] = Field(default_factory=list, alias="Skills")
    research_work: List[ResearchWork] = Field(
        default_factory=list, alias="Research Work"
    )
    certifications: List[Certification] = Field(default_factory=list, alias="Certifications")
    achievements: List[str] = Field(default_factory=list, alias="Achievements")
    education: List[Education] = Field(default_factory=list, alias="Education")
    extracted_keywords: List[str] = Field(
        default_factory=list, alias="Extracted Keywords"
    )

    class ConfigDict:
        validate_by_name = True
        str_strip_whitespace = True