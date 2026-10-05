from app.repositories.degree_progress import DegreeProgressRepository
from app.schemas.degree_progress import (
    CompletedCourseProgress,
    DegreeProgressData,
    OutstandingRequirement,
)


class DegreeProgressService:
    def __init__(self, repository: DegreeProgressRepository):
        self.repository = repository

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
