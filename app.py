import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="DestinyPath Chart API", version="1.0.0")


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
    # Cloud Run 健康检查：容器必须启动后立刻可响应
    return {"status": "ok"}


@app.get("/v1/version")
def version():
    # 查看当前依赖版本，便于排错
    try:
        import kerykeion  # type: ignore
        kv = getattr(kerykeion, "__version__", "unknown")
    except Exception as e:
        kv = f"import_failed: {e}"
    return {"service": "destinypath-chart-api", "kerykeion_version": kv}


def _safe_to_obj(subject):
    """
    将 subject 转成可序列化对象（dict），兼容不同 kerykeion / pydantic 版本。
    """
    # 1) 优先 json()，但它常返回字符串 JSON
    if hasattr(subject, "json"):
        try:
            s = subject.json()
            if isinstance(s, str):
                return json.loads(s)
            return s
        except Exception:
            pass

    # 2) pydantic v2
    if hasattr(subject, "model_dump"):
        try:
            return subject.model_dump()
        except Exception:
            pass

    # 3) pydantic v1
    if hasattr(subject, "dict"):
        try:
            return subject.dict()
        except Exception:
            pass

    # 4) to_dict()
    if hasattr(subject, "to_dict"):
        try:
            return subject.to_dict()
        except Exception:
            pass

    # 5) __dict__
    if hasattr(subject, "__dict__"):
        try:
            return subject.__dict__
        except Exception:
            pass

    # 6) fallback
    return {"_raw": str(subject)}


def _extract_preview(subject_obj: dict) -> dict:
    """
    30% 预览字段（给前端/WordPress好用的精简结构）。
    你后面可以按业务再裁剪/改名。
    """
    preview = {}

    for k in ["name", "year", "month", "day", "hour", "minute", "tz_str", "lat", "lng"]:
        if k in subject_obj:
            preview[k] = subject_obj.get(k)

    # 常见字段
    for k in ["zodiac_type", "houses_system_identifier", "houses_system_name", "retrograde_type",
              "iso_formatted_local_datetime", "iso_formatted_utc_datetime", "julian_day"]:
        if k in subject_obj:
            preview[k] = subject_obj.get(k)

    # 行星（通常在 subject_obj 里以 sun/moon/mercury...）
    planets = {}
    for pk in ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]:
        if pk in subject_obj and isinstance(subject_obj.get(pk), dict):
            p = subject_obj.get(pk, {})
            planets[pk] = {
                "sign": p.get("sign"),
                "sign_num": p.get("sign_num"),
                "position": p.get("position"),
                "abs_pos": p.get("abs_pos"),
                "retrograde": p.get("retrograde"),
                "house": p.get("house"),
                "element": p.get("element"),
                "quality": p.get("quality"),
            }

    if planets:
        preview["planets"] = planets

    return preview


@app.post("/v1/natal")
def natal(x: NatalIn):
    try:
        # ✅ 关键：延迟导入，避免容器启动阶段卡死/崩溃
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
            raise RuntimeError("kerykeion API mismatch: cannot import AstrologicalSubject or AstrologicalSubjectFactory")

        # ✅ 创建 subject（兼容不同版本参数名）
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
                # 某些版本用 lon 而非 lng
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

        subject_obj = _safe_to_obj(subject)

        return {
            "ok": True,
            "preview_30": _extract_preview(subject_obj),
            "subject_full": subject_obj,  # 给 DeepSeek/后端用：完整盘面数据
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
