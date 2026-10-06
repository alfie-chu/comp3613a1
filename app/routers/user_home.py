from datetime import date

from fastapi import Request
from fastapi.responses import HTMLResponse
from app.dependencies.session import SessionDep
from app.dependencies.auth import AuthDep
from app.repositories.degree_progress import DegreeProgressRepository
from app.repositories.semester_plan import SemesterPlanRepository
from app.services.degree_progress import DegreeProgressService
from app.services.semester_plan import SemesterPlanService
from . import router, templates


@router.get("/app", response_class=HTMLResponse)
async def user_home_view(
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    repository = DegreeProgressRepository(db)
    service = DegreeProgressService(repository)
    progress = service.get_progress_for_student(user.id)
    plan_repository = SemesterPlanRepository(db)
    plan_service = SemesterPlanService(plan_repository)
    current_plan = plan_service.get_dashboard_summary(user.id)
    programmes = service.get_active_programmes()
    start_years = range(date.today().year - 5, date.today().year + 1)

    return templates.TemplateResponse(
        request=request, 
        name="app.html",
        context={
            "user": user,
            "progress": progress,
            "current_plan": current_plan,
            "programmes": programmes,
            "start_years": start_years,
        }
    )