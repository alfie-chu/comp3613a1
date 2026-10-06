from datetime import datetime

from pydantic import BaseModel


class CompletedCourseProgress(BaseModel):
    course_code: str
    title: str
    credits: int
    grade: str
    completed_at: datetime
    academic_year: int
    semester_number: int


class OutstandingRequirement(BaseModel):
    course_code: str
    title: str
    requirement_type: str
    completion_rule: str


class DegreeProgressData(BaseModel):
    programme_name: str
    status: str
    completed_credits: int
    total_credits_required: int
    progress_percent: int
    completed_courses: list[CompletedCourseProgress]
    outstanding_requirements: list[OutstandingRequirement]
