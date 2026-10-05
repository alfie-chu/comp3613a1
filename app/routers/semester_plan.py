from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status
from sqlmodel import Session

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.repositories.semester_plan import SemesterPlanRepository
from app.services.semester_plan import (
    SemesterPlanNotDeletableError,
    SemesterPlanNotEditableError,
    SemesterPlanNotFoundError,
    SemesterPlanService,
    StudentProfileMissingError,
)
from app.utilities.flash import flash
from . import router, templates


def _service(db: Session) -> SemesterPlanService:
    return SemesterPlanService(SemesterPlanRepository(db))


@router.get("/semester-plan", response_class=HTMLResponse, name="semester_plan_view")
async def semester_plan_view(
    request: Request,
    user: AuthDep,
    db: SessionDep,
    q: str = "",
    plan_id: int | None = None,
    semester_id: int | None = None,
    academic_year: int | None = None,
    semester_number: int | None = None,
):
    service = _service(db)
    try:
        plan_view = service.get_editor_data(
            user.id,
            q,
            plan_id,
            semester_id,
            academic_year,
            semester_number,
        )
        if plan_id is None and plan_view.get("current_semester") is not None:
            plan = service.start_plan(
                user.id,
                plan_view["current_semester"].id,
            )
            plan_view = service.get_editor_data(user.id, q, plan.id)
    except SemesterPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="semester-plan.html",
        context={"user": user, "plan_view": plan_view},
    )


@router.post("/semester-plan/start", name="semester_plan_start")
def semester_plan_start(
    request: Request,
    user: AuthDep,
    db: SessionDep,
    semester_id: int = Form(),
):
    try:
        plan = _service(db).start_plan(user.id, semester_id)
    except (StudentProfileMissingError, SemesterPlanNotFoundError) as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            url=request.url_for("my_plans_view"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    flash(request, "Draft semester plan started.")
    return RedirectResponse(
        url=request.url_for("semester_plan_view").include_query_params(
            plan_id=plan.id
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/my-plans/{plan_id}/delete",
    name="my_plan_delete",
)
def my_plan_delete(
    plan_id: int,
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    try:
        _service(db).delete_draft_plan(user.id, plan_id)
    except (
        StudentProfileMissingError,
        SemesterPlanNotFoundError,
        SemesterPlanNotDeletableError,
    ) as exc:
        flash(request, str(exc), "danger")
    else:
        flash(request, "Draft semester plan deleted.", "success")

    return RedirectResponse(
        url=request.url_for("my_plans_view"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/semester-plan/{plan_id}/courses/add",
    name="semester_plan_add_course",
)
def semester_plan_add_course(
    plan_id: int,
    request: Request,
    user: AuthDep,
    db: SessionDep,
    offering_id: int = Form(),
):
    try:
        _service(db).add_course(user.id, plan_id, offering_id)
    except (
        StudentProfileMissingError,
        SemesterPlanNotFoundError,
        SemesterPlanNotEditableError,
    ) as exc:
        flash(request, str(exc), "danger")
    else:
        flash(request, "Course added to your draft plan.")
    return RedirectResponse(
        url=request.url_for("semester_plan_view").include_query_params(
            plan_id=plan_id
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/semester-plan/{plan_id}/courses/{selection_id}/remove",
    name="semester_plan_remove_course",
)
def semester_plan_remove_course(
    plan_id: int,
    selection_id: int,
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    try:
        _service(db).remove_course(user.id, plan_id, selection_id)
    except (
        StudentProfileMissingError,
        SemesterPlanNotFoundError,
        SemesterPlanNotEditableError,
    ) as exc:
        flash(request, str(exc), "danger")
    else:
        flash(request, "Course removed from your draft plan.")
    return RedirectResponse(
        url=request.url_for("semester_plan_view").include_query_params(
            plan_id=plan_id
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/semester-plan/{plan_id}/save",
    name="semester_plan_save",
)
def semester_plan_save(
    plan_id: int,
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    try:
        _service(db).save_draft(user.id, plan_id)
    except (
        StudentProfileMissingError,
        SemesterPlanNotFoundError,
        SemesterPlanNotEditableError,
    ) as exc:
        flash(request, str(exc), "danger")
    else:
        flash(request, "Draft plan saved.")
    return RedirectResponse(
        url=request.url_for("semester_plan_view").include_query_params(
            plan_id=plan_id
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/semester-plan/{plan_id}/summary",
    response_class=HTMLResponse,
    name="semester_plan_summary_view",
)
async def semester_plan_summary_view(
    plan_id: int,
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    try:
        summary = _service(db).get_summary_data(user.id, plan_id)
    except (StudentProfileMissingError, SemesterPlanNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="semester-plan-summary.html",
        context={"user": user, "summary": summary},
    )


@router.post(
    "/semester-plan/{plan_id}/submit",
    name="semester_plan_submit",
)
def semester_plan_submit(
    plan_id: int,
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    try:
        _service(db).submit_for_review(user.id, plan_id)
    except (
        StudentProfileMissingError,
        SemesterPlanNotFoundError,
        SemesterPlanNotEditableError,
    ) as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            url=request.url_for("semester_plan_view"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    flash(request, "Semester plan submitted for advisor review.")
    return RedirectResponse(
        url=request.url_for("my_plans_view"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/my-plans", response_class=HTMLResponse, name="my_plans_view")
async def my_plans_view(
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    history = _service(db).get_my_plans_data(user.id)
    return templates.TemplateResponse(
        request=request,
        name="my-plans.html",
        context={"user": user, "history": history},
    )


@router.get(
    "/my-plans/{plan_id}",
    response_class=HTMLResponse,
    name="my_plan_detail_view",
)
async def my_plan_detail_view(
    plan_id: int,
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    try:
        plan_detail = _service(db).get_plan_detail(user.id, plan_id)
    except (StudentProfileMissingError, SemesterPlanNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request=request,
        name="my-plan-detail.html",
        context={"user": user, "plan_detail": plan_detail},
    )
