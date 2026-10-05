from datetime import datetime

from sqlmodel import Session, select

from app.models.approval import Advisor, ApprovalRequest
from app.models.degree_progress import (
    Course,
    CourseCompletion,
    DegreePlan,
    Semester,
)
from app.models.semester_plan import CourseOffering, CourseSelection, SemesterPlan
from app.models.student import Student


class ApprovalRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_advisor_by_user_id(self, user_id: int):
        statement = select(Advisor).where(Advisor.user_id == user_id)
        return self.db.exec(statement).one_or_none()

    def get_pending_requests(self):
        statement = (
            select(ApprovalRequest, SemesterPlan, Student, Semester, DegreePlan)
            .join(
                SemesterPlan,
                ApprovalRequest.semester_plan_id == SemesterPlan.id,
            )
            .join(Student, SemesterPlan.student_id == Student.id)
            .join(Semester, SemesterPlan.semester_id == Semester.id)
            .join(DegreePlan, Student.degree_plan_id == DegreePlan.id)
            .where(ApprovalRequest.status == "pending")
            .order_by(ApprovalRequest.submitted_at)
        )
        return list(self.db.exec(statement).all())

    def get_request_for_review(self, request_id: int):
        statement = (
            select(ApprovalRequest, SemesterPlan, Student, Semester, DegreePlan)
            .join(
                SemesterPlan,
                ApprovalRequest.semester_plan_id == SemesterPlan.id,
            )
            .join(Student, SemesterPlan.student_id == Student.id)
            .join(Semester, SemesterPlan.semester_id == Semester.id)
            .join(DegreePlan, Student.degree_plan_id == DegreePlan.id)
            .where(ApprovalRequest.id == request_id)
        )
        return self.db.exec(statement).one_or_none()

    def get_selected_courses(self, plan_id: int):
        statement = (
            select(CourseSelection, CourseOffering, Course)
            .join(
                CourseOffering,
                CourseSelection.course_offering_id == CourseOffering.id,
            )
            .join(Course, CourseOffering.course_id == Course.id)
            .where(CourseSelection.semester_plan_id == plan_id)
        )
        return list(self.db.exec(statement).all())

    def get_completed_credits(self, student_id: int) -> int:
        statement = (
            select(CourseCompletion.course_id, Course.credits)
            .join(Course, CourseCompletion.course_id == Course.id)
            .where(CourseCompletion.student_id == student_id)
        )
        credits_by_course = {
            course_id: credits
            for course_id, credits in self.db.exec(statement).all()
        }
        return sum(credits_by_course.values())

    def review_request(
        self,
        approval_request: ApprovalRequest,
        semester_plan: SemesterPlan,
        advisor_id: int,
        outcome: str,
        comments: str,
    ) -> None:
        now = datetime.now()
        approval_request.advisor_id = advisor_id
        approval_request.status = outcome
        approval_request.advisor_comments = comments
        approval_request.reviewed_at = now

        semester_plan.status = outcome
        self.db.add(approval_request)
        self.db.add(semester_plan)
        self.db.commit()
