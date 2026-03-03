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
        # ✅ 兼容不同 kerykeion 版本：优先 AstrologicalSubject，其次尝试工厂
        AstrologicalSubject = None
        AstrologicalSubjectFactory = None

        try:
            # 常见版本：直接有 AstrologicalSubject
            from kerykeion import AstrologicalSubject  # type: ignore
            AstrologicalSubject = AstrologicalSubject
        except Exception:
            pass

        try:
            # 你原先用的工厂（部分版本才有）
            from kerykeion import AstrologicalSubjectFactory  # type: ignore
            AstrologicalSubjectFactory = AstrologicalSubjectFactory
        except Exception:
            pass

        if AstrologicalSubject is None and AstrologicalSubjectFactory is None:
            raise RuntimeError("kerykeion API mismatch: cannot import AstrologicalSubject or AstrologicalSubjectFactory")

        # ✅ ChartDataFactory 也做延迟导入
        from kerykeion.chart_data_factory import ChartDataFactory  # type: ignore

        if AstrologicalSubject is not None:
            # ✅ 尝试以最常见构造方式创建（不同版本参数名可能不同）
            try:
                subject = AstrologicalSubject(
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
            except TypeError:
                # 有的版本字段名是 lon/lat 或 timezone
                subject = AstrologicalSubject(
                    name=x.name,
                    year=x.year,
                    month=x.month,
                    day=x.day,
                    hour=x.hour,
                    minute=x.minute,
                    lon=x.lng,
                    lat=x.lat,
                    tz_str=x.tz_str,
                    online=False,
                )
        else:
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
