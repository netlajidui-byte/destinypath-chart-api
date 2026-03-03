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
        # 1) 兼容导入：优先 AstrologicalSubject
        AstrologicalSubject = None
        AstrologicalSubjectFactory = None

        try:
            from kerykeion import AstrologicalSubject  # type: ignore
            AstrologicalSubject = AstrologicalSubject
        except Exception:
            pass

        try:
            from kerykeion import AstrologicalSubjectFactory  # type: ignore
            AstrologicalSubjectFactory = AstrologicalSubjectFactory
        except Exception:
            pass

        if AstrologicalSubject is None and AstrologicalSubjectFactory is None:
            raise RuntimeError(
                "kerykeion API mismatch: cannot import AstrologicalSubject/AstrologicalSubjectFactory"
            )

        # 2) 创建 subject（兼容参数名差异）
        if AstrologicalSubject is not None:
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
                subject = AstrologicalSubject(
                    name=x.name,
                    year=x.year,
                    month=x.month,
                    day=x.day,
                    hour=x.hour,
                    minute=x.minute,
                    lon=x.lng,   # 某些版本用 lon
                    lat=x.lat,
                    tz_str=x.tz_str,
                    online=False,
                )
        else:
            # 工厂方式（如果存在）
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

        # 3) 不同版本的 kerykeion 导出方法不一样，做探测：
        #    常见：.json(), .model_dump(), .dict(), .to_dict(), __dict__
        if hasattr(subject, "json"):
            try:
                return {"subject": subject.json()}
            except Exception:
                pass

        if hasattr(subject, "model_dump"):
            try:
                return {"subject": subject.model_dump()}
            except Exception:
                pass

        if hasattr(subject, "dict"):
            try:
                return {"subject": subject.dict()}
            except Exception:
                pass

        if hasattr(subject, "to_dict"):
            try:
                return {"subject": subject.to_dict()}
            except Exception:
                pass

        # 最后兜底：返回 __dict__（大多数对象都有）
        if hasattr(subject, "__dict__"):
            return {"subject": subject.__dict__}

        return {"subject": str(subject)}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
