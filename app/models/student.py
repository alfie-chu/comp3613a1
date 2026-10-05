from sqlmodel import Field, SQLModel


class Student(SQLModel, table=True):
    __tablename__ = "student"

    id: int | None = Field(default=None, primary_key=True)
    student_number: str = Field(index=True, unique=True)
    first_name: str
    last_name: str
    email: str = Field(index=True)
    degree_plan_id: int = Field(foreign_key="degree_plan.id")
    status: str = "active"
    user_id: int = Field(foreign_key="user.id", unique=True, index=True)
