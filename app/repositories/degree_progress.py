from datetime import datetime

from sqlmodel import Session, select

from app.models.degree_progress import (
    Course,
    CourseCompletion,
    DegreePlan,
    DegreeRequirement,
    ProgrammeCatalogue,
    ProgrammeCourseMapping,
    Semester,
)
from app.models.student import Student


class DegreeProgressRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_student_by_user_id(self, user_id: int) -> Student | None:
        statement = select(Student).where(Student.user_id == user_id)
        return self.db.exec(statement).one_or_none()

    def get_student_by_number(self, student_number: str) -> Student | None:
        statement = select(Student).where(
            Student.student_number == student_number.strip()
        )
        return self.db.exec(statement).one_or_none()

    def get_active_programmes(self) -> list[ProgrammeCatalogue]:
        statement = (
            select(ProgrammeCatalogue)
            .where(ProgrammeCatalogue.status == "active")
            .order_by(ProgrammeCatalogue.programme_name)
        )
        return list(self.db.exec(statement).all())

    def get_programme_by_id(self, programme_id: int) -> ProgrammeCatalogue | None:
        statement = select(ProgrammeCatalogue).where(
            ProgrammeCatalogue.id == programme_id
        )
        return self.db.exec(statement).one_or_none()

    def get_programme_by_name(self, programme_name: str) -> ProgrammeCatalogue | None:
        statement = (
            select(ProgrammeCatalogue)
            .where(ProgrammeCatalogue.programme_name == programme_name)
            .order_by(ProgrammeCatalogue.id)
        )
        return self.db.exec(statement).first()

    def get_programme_course_mappings(
        self,
        programme_id: int,
    ) -> list[ProgrammeCourseMapping]:
        statement = select(ProgrammeCourseMapping).where(
            ProgrammeCourseMapping.programme_id == programme_id
        )
        return list(self.db.exec(statement).all())

    def get_programme_courses(self, programme_id: int) -> list[Course]:
        statement = (
            select(Course)
            .join(
                ProgrammeCourseMapping,
                ProgrammeCourseMapping.course_id == Course.id,
            )
            .where(ProgrammeCourseMapping.programme_id == programme_id)
            .order_by(Course.course_code)
        )
        return list(self.db.exec(statement).all())

    def create_student_profile(
        self,
        *,
        user_id: int,
        email: str,
        student_number: str,
        first_name: str,
        last_name: str,
        programme_id: int,
        start_year: int,
    ) -> Student:
        programme = self.get_programme_by_id(programme_id)
        if programme is None:
            raise ValueError(f"Programme {programme_id} does not exist")

        mappings = self.get_programme_course_mappings(programme_id)

        degree_plan = DegreePlan(
            programme_id=programme.id,
            programme_name=programme.programme_name,
            total_credits_required=programme.total_credits_required,
            start_year=start_year,
            end_year=(start_year + programme.standard_duration_years - 1),
            status="active",
        )

        self.db.add(degree_plan)
        self.db.flush()

        for m in mappings:
            requirement = DegreeRequirement(
                degree_plan_id=degree_plan.id,
                course_id=m.course_id,
                requirement_type=m.requirement_type,
                is_required=m.is_required,
                completion_rule=m.completion_rule,
            )
            self.db.add(requirement)

        student = Student(
            user_id=user_id,
            student_number=student_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            degree_plan_id=degree_plan.id,
            status="active",
        )
        self.db.add(student)
        self.db.commit()
        self.db.refresh(student)
        return student

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

    def get_or_create_semester(
        self,
        *,
        academic_year: int,
        semester_number: int,
    ) -> Semester:
        next_year = academic_year + 1
        semester_name = f"Semester {semester_number} {academic_year}/{next_year}"
        statement = select(Semester).where(
            Semester.year == academic_year,
            Semester.semester_name == semester_name,
        )
        semester = self.db.exec(statement).first()
        if semester is not None:
            return semester

        dates = {
            1: (datetime(academic_year, 8, 17), datetime(academic_year, 12, 18)),
            2: (datetime(next_year, 1, 12), datetime(next_year, 5, 1)),
            3: (datetime(next_year, 5, 15), datetime(next_year, 8, 5)),
        }
        start_date, end_date = dates[semester_number]
        semester = Semester(
            semester_name=semester_name,
            year=academic_year,
            start_date=start_date.date(),
            end_date=end_date.date(),
        )
        self.db.add(semester)
        self.db.flush()
        return semester

    def create_course_completion(
        self,
        *,
        student_id: int,
        course_id: int,
        grade: str,
        academic_year: int,
        semester_number: int,
    ) -> CourseCompletion:
        semester = self.get_or_create_semester(
            academic_year=academic_year,
            semester_number=semester_number,
        )
        if semester.id is None:
            raise RuntimeError("Unable to save the completion semester.")

        completion = CourseCompletion(
            student_id=student_id,
            course_id=course_id,
            semester_id=semester.id,
            grade=grade,
            academic_year=academic_year,
            semester_number=semester_number,
            completed_at=datetime.now(),
        )
        self.db.add(completion)
        self.db.commit()
        self.db.refresh(completion)
        return completion
