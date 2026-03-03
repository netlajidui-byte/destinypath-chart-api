from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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
    # 确保容器一启动就能立刻响应健康检查
    return {"status": "ok"}

@app.post("/v1/natal")
def natal(x: NatalIn):
    try:
        # ✅ 关键：延迟导入，避免容器启动阶段崩溃/超时
        from kerykeion import AstrologicalSubjectFactory
        from kerykeion.chart_data_factory import ChartDataFactory

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

        # ✅ 兼容：不同版本对象可能没有 model_dump
        def safe_dump(obj):
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "dict"):
                return obj.dict()
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

        return {
            "subject": safe_dump(subject),
            "chart_data": safe_dump(chart_data),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
