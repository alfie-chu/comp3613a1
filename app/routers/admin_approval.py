from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status
from sqlmodel import Session

from app.dependencies.auth import AdminDep
from app.dependencies.session import SessionDep
from app.repositories.approval import ApprovalRepository
from app.services.approval import (
    ApprovalDecisionValidationError,
    ApprovalRequestAlreadyReviewedError,
    ApprovalRequestNotFoundError,
    ApprovalService,
    AdvisorProfileMissingError,
)
from app.utilities.flash import flash
from . import router, templates


def _service(db: Session) -> ApprovalService:
    return ApprovalService(ApprovalRepository(db))


@router.get("/admin/review-plans", response_class=HTMLResponse, name="review_plans_view")
async def review_plans_view(
    request: Request,
    user: AdminDep,
    db: SessionDep,
):
    requests = _service(db).get_pending_approval_requests()
    return templates.TemplateResponse(
        request=request,
        name="review-plans.html",
        context={"user": user, "review_requests": requests},
    )


@router.get(
    "/admin/review-plans/{request_id}",
    response_class=HTMLResponse,
    name="review_plan_detail_view",
)
async def review_plan_detail_view(
    request_id: int,
    request: Request,
    user: AdminDep,
    db: SessionDep,
):
    try:
        review_detail = _service(db).get_review_detail(request_id)
    except ApprovalRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="review-plan-detail.html",
        context={"user": user, "review_detail": review_detail},
    )


@router.post(
    "/admin/review-plans/{request_id}/decision",
    name="review_plan_decision",
)
def review_plan_decision(
    request_id: int,
    request: Request,
    user: AdminDep,
    db: SessionDep,
    outcome: str = Form(),
    comments: str = Form(default=""),
):
    try:
        _service(db).review_plan(user.id, request_id, outcome, comments)
    except (
        AdvisorProfileMissingError,
        ApprovalDecisionValidationError,
        ApprovalRequestAlreadyReviewedError,
        ApprovalRequestNotFoundError,
    ) as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            url=request.url_for("review_plan_detail_view", request_id=request_id),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    flash(request, f"Plan {outcome.replace('_', ' ')}.")
    return RedirectResponse(
        url=request.url_for("review_plans_view"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
