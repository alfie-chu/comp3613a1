from sqlmodel import Session, select

from app.models.degree_progress import (
    Course,
    CourseCompletion,
    DegreePlan,
    DegreeRequirement,
)
from app.models.student import Student


class DegreeProgressRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_student_by_user_id(self, user_id: int) -> Student | None:
        statement = select(Student).where(Student.user_id == user_id)
        return self.db.exec(statement).one_or_none()

    def get_degree_plan(self, degree_plan_id: int) -> DegreePlan | None:
        return self.db.get(DegreePlan, degree_plan_id)

    def get_requirements_with_courses(
        self,
        degree_plan_id: int,
    ) -> list[tuple[DegreeRequirement, Course]]:
        statement = (
            select(DegreeRequirement, Course)
            .join(Course, DegreeRequirement.course_id == Course.id)
            .where(DegreeRequirement.degree_plan_id == degree_plan_id)
        )
        return list(self.db.exec(statement).all())

    def get_completions_with_courses(
        self,
        student_id: int,
    ) -> list[tuple[CourseCompletion, Course]]:
        statement = (
            select(CourseCompletion, Course)
            .join(Course, CourseCompletion.course_id == Course.id)
            .where(CourseCompletion.student_id == student_id)
            .order_by(CourseCompletion.completed_at.desc())
        )
        return list(self.db.exec(statement).all())
