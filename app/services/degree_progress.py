from datetime import date

from app.repositories.degree_progress import DegreeProgressRepository
from app.schemas.degree_progress import (
    CompletedCourseProgress,
    DegreeProgressData,
    OutstandingRequirement,
)
from app.models.degree_progress import Course, CourseCompletion, DegreePlan


COURSE_GRADES = (
    "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F",
)


class DegreeProgressService:
    def __init__(self, repository: DegreeProgressRepository):
        self.repository = repository

    def get_active_programmes(self):
        return self.repository.get_active_programmes()

    def setup_student_profile(
        self,
        *,
        user_id: int,
        email: str,
        student_number: str,
        first_name: str,
        last_name: str,
        programme_id: int,
        start_year: int,
    ):
        current_year = date.today().year
        if start_year < current_year - 5 or start_year > current_year:
            raise ValueError("Choose a start year from the available options.")

        existing_student = self.repository.get_student_by_user_id(user_id)
        if existing_student is not None:
            raise ValueError(f"Student profile already exists for user {user_id}")

        if self.repository.get_student_by_number(student_number) is not None:
            raise ValueError("That student ID is already in use.")

        programme = self.repository.get_programme_by_id(programme_id)
        if programme is None:
            raise ValueError(f"Programme {programme_id} does not exist")

        if programme.status != "active":
            raise ValueError(f"Programme {programme_id} is not active")

        return self.repository.create_student_profile(
            user_id=user_id,
            email=email,
            student_number=student_number,
            first_name=first_name,
            last_name=last_name,
            programme_id=programme_id,
            start_year=start_year,
        )

    def add_course_completion(
        self,
        *,
        user_id: int,
        course_id: int,
        grade: str,
        academic_year: int,
        semester_number: int,
    ) -> CourseCompletion:
        student = self.repository.get_student_by_user_id(user_id)
        if student is None:
            raise ValueError("No student profile found.")

        degree_plan = self.repository.get_degree_plan(student.degree_plan_id)
        if degree_plan is None:
            raise ValueError("No degree plan found.")
        programme_id = self._programme_id_for_plan(degree_plan)
        if programme_id is None:
            raise ValueError("The student's degree plan has no linked programme.")

        mappings = self.repository.get_programme_course_mappings(
            programme_id
        )

        programme_course_ids = {m.course_id for m in mappings}
        if course_id not in programme_course_ids:
            raise ValueError("Choose a course in your degree programme.")

        completions = self.repository.get_completions_with_courses(student.id)
        completed_course_ids = {course.id for _, course in completions}
        if course_id in completed_course_ids:
            raise ValueError("That course is already marked as completed.")

        grade = grade.strip().upper()
        if grade not in COURSE_GRADES:
            raise ValueError("Choose a grade from the available options.")

        if semester_number not in {1, 2, 3}:
            raise ValueError("Choose a semester from the available options.")

        if (
            academic_year < degree_plan.start_year
            or academic_year > date.today().year
        ):
            raise ValueError(
                "Choose an academic year from your start year through this year."
            )

        return self.repository.create_course_completion(
            student_id=student.id,
            course_id=course_id,
            grade=grade,
            academic_year=academic_year,
            semester_number=semester_number,
        )

    def get_course_completion_form_data(
        self,
        user_id: int,
    ) -> tuple[list[Course], list[int]]:
        student = self.repository.get_student_by_user_id(user_id)
        if student is None:
            return [], []

        degree_plan = self.repository.get_degree_plan(student.degree_plan_id)
        if degree_plan is None:
            return [], []

        programme_id = self._programme_id_for_plan(degree_plan)
        if programme_id is None:
            return [], []

        completed_course_ids = {
            course.id
            for _, course in self.repository.get_completions_with_courses(student.id)
        }
        courses = [
            course
            for course in self.repository.get_programme_courses(
                programme_id
            )
            if course.id not in completed_course_ids
        ]
        academic_years = list(
            range(degree_plan.start_year, date.today().year + 1)
        )
        return courses, academic_years

    def _programme_id_for_plan(self, degree_plan: DegreePlan) -> int | None:
        if degree_plan.programme_id is not None:
            return degree_plan.programme_id
        programme = self.repository.get_programme_by_name(
            degree_plan.programme_name
        )
        return programme.id if programme is not None else None

    def get_progress_for_student(self, user_id: int) -> DegreeProgressData | None:
        student = self.repository.get_student_by_user_id(user_id)
        if student is None:
            return None

        degree_plan = self.repository.get_degree_plan(student.degree_plan_id)
        if degree_plan is None:
            raise LookupError(
                f"Degree plan {student.degree_plan_id} was not found for student {student.id}"
            )

        completions = self.repository.get_completions_with_courses(student.id)
        requirements = self.repository.get_requirements_with_courses(
            degree_plan.id
        )

        completed_course_ids = {course.id for _, course in completions}
        credits_by_course = {
            course.id: course.credits for _, course in completions
        }
        completed_credits = sum(credits_by_course.values())

        outstanding_requirements = [
            OutstandingRequirement(
                course_code=course.course_code,
                title=course.title,
                requirement_type=requirement.requirement_type,
                completion_rule=requirement.completion_rule,
            )
            for requirement, course in requirements
            if requirement.is_required and course.id not in completed_course_ids
        ]

        completed_courses = [
            CompletedCourseProgress(
                course_code=course.course_code,
                title=course.title,
                credits=course.credits,
                grade=completion.grade,
                completed_at=completion.completed_at,
                academic_year=completion.academic_year,
                semester_number=completion.semester_number,
            )
            for completion, course in completions
        ]

        total_credits = degree_plan.total_credits_required
        progress_percent = (
            min(round(completed_credits / total_credits * 100), 100)
            if total_credits > 0
            else 0
        )

        return DegreeProgressData(
            programme_name=degree_plan.programme_name,
            status=degree_plan.status,
            completed_credits=completed_credits,
            total_credits_required=total_credits,
            progress_percent=progress_percent,
            completed_courses=completed_courses,
            outstanding_requirements=outstanding_requirements,
        )
