from datetime import date, datetime

from sqlmodel import Field, SQLModel
from sqlalchemy import UniqueConstraint


class DegreePlan(SQLModel, table=True):
    __tablename__ = "degree_plan"

    id: int | None = Field(default=None, primary_key=True)
    programme_id: int | None = Field(default=None, foreign_key="programme_catalogue.id", nullable=True)
    programme_name: str
    total_credits_required: int
    start_year: int
    end_year: int
    status: str = "active"


class Course(SQLModel, table=True):
    __tablename__ = "course"

    id: int | None = Field(default=None, primary_key=True)
    course_code: str = Field(index=True, unique=True)
    title: str
    credits: int
    category: str
    level: str


class DegreeRequirement(SQLModel, table=True):
    __tablename__ = "degree_requirement"

    id: int | None = Field(default=None, primary_key=True)
    degree_plan_id: int = Field(foreign_key="degree_plan.id")
    course_id: int = Field(foreign_key="course.id")
    requirement_type: str
    is_required: bool
    completion_rule: str


class CoursePrerequisite(SQLModel, table=True):
    __tablename__ = "course_prerequisite"

    course_id: int = Field(foreign_key="course.id", primary_key=True)
    prerequisite_course_id: int = Field(
        foreign_key="course.id",
        primary_key=True,
    )


class Semester(SQLModel, table=True):
    __tablename__ = "semester"

    id: int | None = Field(default=None, primary_key=True)
    semester_name: str
    year: int
    start_date: date
    end_date: date


class CourseCompletion(SQLModel, table=True):
    __tablename__ = "course_completion"
    __table_args__ = (UniqueConstraint("student_id", "course_id"),)

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id")
    course_id: int = Field(foreign_key="course.id")
    semester_id: int = Field(foreign_key="semester.id")
    semester_id: int = Field(foreign_key="semester.id")
    academic_year: int
    semester_number: int
    grade: str
    completed_at: datetime
    is_transfer: bool = False


class ProgrammeCatalogue(SQLModel, table=True):
    __tablename__ = "programme_catalogue"

    id: int | None = Field(default=None, primary_key=True)
    programme_name: str
    total_credits_required: int
    standard_duration_years: int
    status: str = "active"

class ProgrammeCourseMapping(SQLModel, table=True):
    __tablename__ = "programme_course_mapping"
    __table_args__ = (UniqueConstraint("programme_id", "course_id"),)

    id: int | None = Field(default=None, primary_key=True)
    programme_id: int = Field(foreign_key="programme_catalogue.id", index=True)
    course_id: int = Field(foreign_key="course.id", index=True)
    requirement_type: str
    is_required: bool
    completion_rule: str