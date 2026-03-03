import os
import json
from typing import Any, Dict, Optional, List, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="DestinyPath Chart API", version="1.1.0")


# -----------------------------
# Input models
# -----------------------------

class NatalIn(BaseModel):
    # Original input model (kept for backward compatibility)
    name: str = "User"
    year: int
    month: int
    day: int
    hour: int
    minute: int
    lng: float
    lat: float
    tz_str: str


class BirthChartIn(BaseModel):
    # WP plugin-friendly model (recommended)
    birth_date: str = Field(..., description="YYYY-MM-DD")
    birth_time: Optional[str] = Field(None, description="HH:MM (24h). Optional if unknown_time=1")
    unknown_time: int = Field(0, description="1 if birth time unknown else 0")
    tz: str = Field(..., description="IANA tz, e.g. Europe/London")
    lat: float
    lng: float
    house_system: str = Field("P", description="Swiss Ephemeris house system letter, e.g. P (Placidus), W (Whole Sign)")


# -----------------------------
# Health / version
# -----------------------------

@app.get("/")
def root():
    # Cloud Run health check: must respond quickly
    return {"status": "ok"}


@app.get("/v1/version")
def version():
    try:
        import kerykeion  # type: ignore
        kv = getattr(kerykeion, "__version__", "unknown")
    except Exception as e:
        kv = f"import_failed: {e}"
    return {
        "service": "destinypath-chart-api",
        "kerykeion_version": kv,
        "port_env": os.getenv("PORT", ""),
    }


# -----------------------------
# Serialization helpers
# -----------------------------

def _safe_to_obj(subject: Any) -> Dict[str, Any]:
    """
    Convert 'subject' into a JSON-serializable dict.
    Works across different kerykeion + pydantic versions.
    """
    # 1) Prefer json() (often returns JSON string)
    if hasattr(subject, "json"):
        try:
            s = subject.json()
            if isinstance(s, str):
                return json.loads(s)
            if isinstance(s, dict):
                return s
        except Exception:
            pass

    # 2) pydantic v2
    if hasattr(subject, "model_dump"):
        try:
            d = subject.model_dump()
            if isinstance(d, dict):
                return d
        except Exception:
            pass

    # 3) pydantic v1
    if hasattr(subject, "dict"):
        try:
            d = subject.dict()
            if isinstance(d, dict):
                return d
        except Exception:
            pass

    # 4) to_dict()
    if hasattr(subject, "to_dict"):
        try:
            d = subject.to_dict()
            if isinstance(d, dict):
                return d
        except Exception:
            pass

    # 5) __dict__
    if hasattr(subject, "__dict__"):
        try:
            d = dict(subject.__dict__)
            if isinstance(d, dict):
                return d
        except Exception:
            pass

    # 6) fallback
    return {"_raw": str(subject)}


def _as_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str) and v.strip() != "":
            return float(v)
    except Exception:
        return None
    return None


def _pick_first_float(obj: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for k in keys:
        if k in obj:
            f = _as_float(obj.get(k))
            if f is not None:
                return f
    return None


# -----------------------------
# Commercial schema extraction
# -----------------------------

_PLANET_KEYS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]
_ANGLE_KEYS = {
    "asc": ["asc", "ascendant", "ASC", "Asc"],
    "mc": ["mc", "midheaven", "MC", "Mc"]
}

def _extract_planets(subject_obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    planets: Dict[str, Dict[str, Any]] = {}

    # Common: planets are on top-level keys (sun/moon/...)
    for pk in _PLANET_KEYS:
        p = subject_obj.get(pk)
        if isinstance(p, dict):
            abs_pos = _pick_first_float(p, ["abs_pos", "absolute_position", "absoluteLongitude", "lon", "longitude"])
            # some versions store 'position' (0-30) + 'sign_num'
            if abs_pos is None:
                sign_num = _as_float(p.get("sign_num"))
                pos = _as_float(p.get("position"))
                if sign_num is not None and pos is not None:
                    abs_pos = sign_num * 30.0 + pos
            planets[pk] = {
                "abs_pos": abs_pos,
                "retrograde": bool(p.get("retrograde", False)),
                "speed": _as_float(p.get("speed")),
                "sign": p.get("sign"),
                "sign_num": p.get("sign_num"),
                "house": p.get("house"),
            }

    # Alternative: planets under a "planets" dict
    if not planets and isinstance(subject_obj.get("planets"), dict):
        pd = subject_obj["planets"]
        for pk in _PLANET_KEYS:
            p = pd.get(pk)
            if isinstance(p, dict):
                abs_pos = _pick_first_float(p, ["abs_pos", "absolute_position", "lon", "longitude"])
                planets[pk] = {
                    "abs_pos": abs_pos,
                    "retrograde": bool(p.get("retrograde", False)),
                    "speed": _as_float(p.get("speed")),
                    "sign": p.get("sign"),
                    "sign_num": p.get("sign_num"),
                    "house": p.get("house"),
                }

    # Remove planets without abs_pos (keep sign-based info if you want; for drawing we need abs_pos)
    planets = {k: v for k, v in planets.items() if v.get("abs_pos") is not None}
    return planets


def _extract_angles(subject_obj: Dict[str, Any]) -> Dict[str, Optional[float]]:
    angles: Dict[str, Optional[float]] = {"asc": None, "mc": None}

    # 1) direct keys on subject
    for outk, candidates in _ANGLE_KEYS.items():
        angles[outk] = _pick_first_float(subject_obj, candidates)

    # 2) nested under 'angles'
    if isinstance(subject_obj.get("angles"), dict):
        ad = subject_obj["angles"]
        for outk, candidates in _ANGLE_KEYS.items():
            if angles[outk] is None:
                angles[outk] = _pick_first_float(ad, candidates)

    # 3) sometimes under objects
    for outk, candidates in _ANGLE_KEYS.items():
        if angles[outk] is None:
            for ck in candidates:
                v = subject_obj.get(ck)
                if isinstance(v, dict):
                    angles[outk] = _pick_first_float(v, ["abs_pos", "lon", "longitude", "value"])
                    if angles[outk] is not None:
                        break

    return angles


def _extract_houses(subject_obj: Dict[str, Any]) -> List[float]:
    """
    Returns 12 house cusps as absolute degrees (0-360), in order: house 1..12.
    """
    # Common: "houses" is a list of dicts with abs_pos or list of floats
    houses = subject_obj.get("houses")
    out: List[float] = []

    if isinstance(houses, list):
        # list of floats
        if houses and isinstance(houses[0], (int, float, str)):
            for v in houses[:12]:
                f = _as_float(v)
                if f is not None:
                    out.append(f % 360.0)
        # list of dicts
        elif houses and isinstance(houses[0], dict):
            for h in houses[:12]:
                f = _pick_first_float(h, ["abs_pos", "lon", "longitude", "cusp", "position"])
                if f is not None:
                    out.append(f % 360.0)

    # Alternative: "houses" dict like {"first_house": {...}, ...}
    if len(out) != 12 and isinstance(houses, dict):
        order = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth"]
        for name in order:
            h = houses.get(f"{name}_house") or houses.get(name) or houses.get(name.title())
            if isinstance(h, dict):
                f = _pick_first_float(h, ["abs_pos", "lon", "longitude", "cusp", "position"])
                if f is not None:
                    out.append(f % 360.0)

    # Alternative: house cusps at top-level keys like "first_house", etc.
    if len(out) != 12:
        order = ["first_house","second_house","third_house","fourth_house","fifth_house","sixth_house",
                 "seventh_house","eighth_house","ninth_house","tenth_house","eleventh_house","twelfth_house"]
        for k in order:
            h = subject_obj.get(k)
            if isinstance(h, dict):
                f = _pick_first_float(h, ["abs_pos", "lon", "longitude", "cusp", "position"])
                if f is not None:
                    out.append(f % 360.0)

    # Sanity
    if len(out) != 12:
        return []
    return out


def _extract_aspects(subject_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Optional: aspects list if present.
    Commercial frontends can use it; otherwise they can compute client-side.
    """
    aspects = subject_obj.get("aspects")
    out: List[Dict[str, Any]] = []
    if isinstance(aspects, list):
        for a in aspects:
            if isinstance(a, dict):
                out.append({
                    "p1": a.get("p1") or a.get("planet_1") or a.get("from"),
                    "p2": a.get("p2") or a.get("planet_2") or a.get("to"),
                    "type": a.get("type") or a.get("aspect") or a.get("name"),
                    "orb": _as_float(a.get("orb")),
                    "exact": _as_float(a.get("exact")),
                })
    return out


def to_commercial_chart(subject_obj: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a stable, professional 'chart_json' schema for your WP plugin + JS engine.
    """
    angles = _extract_angles(subject_obj)
    houses = _extract_houses(subject_obj)
    planets = _extract_planets(subject_obj)
    aspects = _extract_aspects(subject_obj)

    chart = {
        "meta": meta,
        "angles": angles,
        "houses": houses,
        "planets": planets,
        "aspects": aspects,
        # Keep a couple of useful identifiers if present:
        "zodiac_type": subject_obj.get("zodiac_type"),
        "houses_system_identifier": subject_obj.get("houses_system_identifier"),
        "houses_system_name": subject_obj.get("houses_system_name"),
    }
    return chart


def _extract_preview_30(subject_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    30% preview fields: concise and frontend-friendly.
    """
    preview: Dict[str, Any] = {}
    for k in [
        "name","year","month","day","hour","minute","tz_str","lat","lng",
        "zodiac_type","houses_system_identifier","houses_system_name",
        "retrograde_type","iso_formatted_local_datetime","iso_formatted_utc_datetime","julian_day"
    ]:
        if k in subject_obj:
            preview[k] = subject_obj.get(k)

    planets = {}
    for pk in _PLANET_KEYS:
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


# -----------------------------
# Kerykeion subject creation (version-safe)
# -----------------------------

def _create_subject_from_natal(x: NatalIn):
    """
    Creates kerykeion AstrologicalSubject using whatever API is available.
    """
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

    if AstrologicalSubject is not None:
        try:
            return AstrologicalSubject(
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
            # some versions use lon not lng
            return AstrologicalSubject(
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

    # Factory method
    try:
        return AstrologicalSubjectFactory.from_birth_data(
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
        return AstrologicalSubjectFactory.from_birth_data(
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


def _birth_to_natal(x: BirthChartIn) -> NatalIn:
    # birth_date: YYYY-MM-DD
    try:
        y, m, d = x.birth_date.split("-")
        year = int(y); month = int(m); day = int(d)
    except Exception:
        raise HTTPException(status_code=422, detail="birth_date must be YYYY-MM-DD")

    hour = 12
    minute = 0
    if int(x.unknown_time) != 1:
        if not x.birth_time:
            raise HTTPException(status_code=422, detail="birth_time required when unknown_time=0")
        try:
            hh, mm = x.birth_time.split(":")
            hour = int(hh); minute = int(mm)
        except Exception:
            raise HTTPException(status_code=422, detail="birth_time must be HH:MM")

    return NatalIn(
        name="User",
        year=year, month=month, day=day,
        hour=hour, minute=minute,
        lng=float(x.lng), lat=float(x.lat),
        tz_str=str(x.tz),
    )


# -----------------------------
# Routes
# -----------------------------

@app.post("/v1/natal")
def natal(x: NatalIn):
    """
    Backward compatible endpoint.
    Returns:
    - chart_json: stable schema for frontend drawing + WP plugin
    - preview_30: small preview fields
    - subject_full: raw dump (for DeepSeek prompt)
    """
    try:
        subject = _create_subject_from_natal(x)
        subject_obj = _safe_to_obj(subject)

        meta = {
            "name": x.name,
            "year": x.year, "month": x.month, "day": x.day,
            "hour": x.hour, "minute": x.minute,
            "tz": x.tz_str,
            "lat": x.lat, "lng": x.lng,
        }

        chart_json = to_commercial_chart(subject_obj, meta)

        return {
            "ok": True,
            "chart_json": chart_json,
            "preview_30": _extract_preview_30(subject_obj),
            "subject_full": subject_obj,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/v1/birth-chart")
def birth_chart(x: BirthChartIn):
    """
    WP plugin recommended endpoint.
    Accepts {birth_date, birth_time, unknown_time, tz, lat, lng, house_system}
    NOTE: house_system is accepted for forward-compat; if your kerykeion build doesn't support it,
          we still return chart based on kerykeion default.
    """
    try:
        natal_in = _birth_to_natal(x)
        subject = _create_subject_from_natal(natal_in)
        subject_obj = _safe_to_obj(subject)

        meta = {
            "name": natal_in.name,
            "birth_date": x.birth_date,
            "birth_time": x.birth_time,
            "unknown_time": int(x.unknown_time),
            "tz": x.tz,
            "lat": x.lat, "lng": x.lng,
            "house_system": (x.house_system or "P"),
        }

        chart_json = to_commercial_chart(subject_obj, meta)

        return {
            "ok": True,
            "chart_json": chart_json,
            "preview_30": _extract_preview_30(subject_obj),
            "subject_full": subject_obj,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
