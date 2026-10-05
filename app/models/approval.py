from datetime import datetime

from sqlmodel import Field, SQLModel


class Advisor(SQLModel, table=True):
    __tablename__ = "advisor"

    id: int | None = Field(default=None, primary_key=True)
    first_name: str
    last_name: str
    email: str
    department: str
    user_id: int = Field(foreign_key="user.id", unique=True, index=True)


class ApprovalRequest(SQLModel, table=True):
    __tablename__ = "approval_request"

    id: int | None = Field(default=None, primary_key=True)
    semester_plan_id: int = Field(foreign_key="semester_plan.id")
    advisor_id: int | None = Field(default=None, foreign_key="advisor.id")
    status: str = "pending"
    rationale: str = ""
    advisor_comments: str = ""
    submitted_at: datetime
    reviewed_at: datetime | None = None
