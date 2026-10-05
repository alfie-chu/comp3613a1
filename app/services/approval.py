from typing import Any

from app.repositories.approval import ApprovalRepository


class AdvisorProfileMissingError(LookupError):
    pass


class ApprovalRequestNotFoundError(LookupError):
    pass


class ApprovalRequestAlreadyReviewedError(ValueError):
    pass


class ApprovalDecisionValidationError(ValueError):
    pass


class ApprovalService:
    def __init__(self, repository: ApprovalRepository):
        self.repository = repository

    def get_pending_approval_requests(self):
        pending = []
        for approval, plan, student, semester, degree_plan in (
            self.repository.get_pending_requests()
        ):
            completed_credits = self.repository.get_completed_credits(student.id)
            required_credits = degree_plan.total_credits_required
            progress_percent = (
                min(round(completed_credits / required_credits * 100), 100)
                if required_credits > 0
                else 0
            )
            pending.append(
                {
                    "approval": approval,
                    "plan": plan,
                    "student": student,
                    "semester": semester,
                    "degree_plan": degree_plan,
                    "progress_percent": progress_percent,
                }
            )
        return pending

    def review_plan(self, user_id: int, request_id: int, outcome: str, comments: str):
        if outcome not in {"approved", "revision_required", "rejected"}:
            raise ApprovalDecisionValidationError("Choose a valid review decision.")
        if outcome in {"revision_required", "rejected"} and not comments.strip():
            raise ApprovalDecisionValidationError(
                "Add advisor comments when requesting a revision or rejecting a plan."
            )

        advisor = self.repository.get_advisor_by_user_id(user_id)
        if advisor is None:
            raise AdvisorProfileMissingError(
                "This administrator account is not linked to an advisor profile."
            )
        row = self.repository.get_request_for_review(request_id)
        if row is None:
            raise ApprovalRequestNotFoundError("Approval request not found.")
        approval_request, semester_plan, _, _, _ = row
        if approval_request.status != "pending":
            raise ApprovalRequestAlreadyReviewedError(
                "This approval request has already been reviewed."
            )

        self.repository.review_request(
            approval_request,
            semester_plan,
            advisor.id,
            outcome,
            comments.strip(),
        )

    def get_review_detail(self, request_id: int) -> dict[str, Any]:
        row = self.repository.get_request_for_review(request_id)
        if row is None:
            raise ApprovalRequestNotFoundError("Approval request not found.")
        approval, plan, student, semester, degree_plan = row
        completed_credits = self.repository.get_completed_credits(student.id)
        required_credits = degree_plan.total_credits_required
        selected_courses = self.repository.get_selected_courses(plan.id)
        return {
            "approval": approval,
            "plan": plan,
            "student": student,
            "semester": semester,
            "degree_plan": degree_plan,
            "completed_credits": completed_credits,
            "progress_percent": (
                min(round(completed_credits / required_credits * 100), 100)
                if required_credits > 0
                else 0
            ),
            "selected_courses": selected_courses,
            "planned_credits": sum(course.credits for _, _, course in selected_courses),
        }
