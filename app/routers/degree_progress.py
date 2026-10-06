from datetime import date

from fastapi import Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.repositories.degree_progress import DegreeProgressRepository
from app.services.degree_progress import COURSE_GRADES, DegreeProgressService
from app.utilities.flash import flash
from . import router, templates


@router.get("/degree", response_class=HTMLResponse, name="degree_progress_view")
async def degree_progress_view(
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    repository = DegreeProgressRepository(db)
    service = DegreeProgressService(repository)
    progress = service.get_progress_for_student(user.id)
    programmes = service.get_active_programmes()
    start_years = range(date.today().year - 5, date.today().year + 1)
    completion_courses, completion_academic_years = (
        service.get_course_completion_form_data(user.id)
    )

    return templates.TemplateResponse(
        request=request,
        name="degree-progress.html",
        context={
            "user": user,
            "progress": progress,
            "programmes": programmes,
            "start_years": start_years,
            "completion_courses": completion_courses,
            "completion_academic_years": completion_academic_years,
            "completion_grades": COURSE_GRADES,
        },
    )


@router.post("/degree", response_class=HTMLResponse, name="degree_progress_create")
def degree_progress_create(
    request: Request,
    user: AuthDep,
    db: SessionDep,
    student_number: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    programme_id: int = Form(...),
    start_year: int = Form(...),
):
    repository = DegreeProgressRepository(db)
    service = DegreeProgressService(repository)

    try:
        service.setup_student_profile(
            user_id=user.id,
            email=user.email,
            student_number=student_number,
            first_name=first_name,
            last_name=last_name,
            programme_id=programme_id,
            start_year=start_year,
        )
    except ValueError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            url=request.url_for("user_home_view"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    flash(
        request,
        "Student profile setup complete. Your degree progress is now available.",
    )
    return RedirectResponse(
        url=request.url_for("degree_progress_view"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/degree/completions",
    response_class=HTMLResponse,
    name="degree_completion_create",
)
def degree_completion_create(
    request: Request,
    user: AuthDep,
    db: SessionDep,
    course_id: int = Form(...),
    grade: str = Form(...),
    academic_year: int = Form(...),
    semester_number: int = Form(...),
):
    repository = DegreeProgressRepository(db)
    service = DegreeProgressService(repository)

    try:
        service.add_course_completion(
            user_id=user.id,
            course_id=course_id,
            grade=grade,
            academic_year=academic_year,
            semester_number=semester_number,
        )
    except ValueError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(
            url=request.url_for("degree_progress_view"),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    flash(request, "Course completion added. Your degree progress is updated.")
    return RedirectResponse(
        url=request.url_for("degree_progress_view"),
        status_code=status.HTTP_303_SEE_OTHER,
    )