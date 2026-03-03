from fastapi import FastAPI
from pydantic import BaseModel
from kerykeion import AstrologicalSubjectFactory
from kerykeion.chart_data_factory import ChartDataFactory

app = FastAPI(title="DestinyPath Chart API")

class NatalIn(BaseModel):
    name: str = "User"
    year: int
    month: int
    day: int
    hour: int
    minute: int
    lng: float
    lat: float
    tz_str: str

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/v1/natal")
def natal(x: NatalIn):
    subject = AstrologicalSubjectFactory.from_birth_data(
        name=x.name,
        year=x.year,
        month=x.month,
        day=x.day,
        hour=x.hour,
        minute=x.minute,
        lng=x.lng,
        lat=x.lat,
        tz_str=x.tz_str,
        online=False,
    )

    chart_data = ChartDataFactory.create_natal_chart_data(subject)

    return {
        "subject": subject.model_dump(),
        "chart_data": chart_data.model_dump(),
    }
