"""Database table models.

Import every table model here so ``SQLModel.metadata.create_all`` sees them.
"""

from app.models.user import User
from app.models.student import Student
from app.models.degree_progress import (
    Course,
    CourseCompletion,
    CoursePrerequisite,
    DegreePlan,
    DegreeRequirement,
    Semester,
)
from app.models.semester_plan import CourseOffering, CourseSelection, SemesterPlan
from app.models.approval import Advisor, ApprovalRequest

__all__ = [
    "User",
    "Student",
    "DegreePlan",
    "DegreeRequirement",
    "Course",
    "Semester",
    "CourseCompletion",
    "CoursePrerequisite",
    "CourseOffering",
    "SemesterPlan",
    "CourseSelection",
    "Advisor",
    "ApprovalRequest",
]
