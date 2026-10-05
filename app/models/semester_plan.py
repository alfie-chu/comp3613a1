from datetime import datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class SemesterPlan(SQLModel, table=True):
    __tablename__ = "semester_plan"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id")
    semester_id: int = Field(foreign_key="semester.id")
    status: str = "planning"
    created_at: datetime = Field(default_factory=datetime.now)
    submitted_at: datetime | None = Field(default=None)


class CourseOffering(SQLModel, table=True):
    __tablename__ = "course_offering"
    __table_args__ = (
        UniqueConstraint("course_id", "semester_id", "section"),
    )

    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id")
    semester_id: int = Field(foreign_key="semester.id")
    section: str
    delivery_mode: str
    status: str = "open"


class CourseSelection(SQLModel, table=True):
    __tablename__ = "course_selection"
    __table_args__ = (
        UniqueConstraint("semester_plan_id", "course_offering_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    semester_plan_id: int = Field(foreign_key="semester_plan.id")
    course_offering_id: int = Field(foreign_key="course_offering.id")
    status: str = "selected"
    notes: str | None = None
