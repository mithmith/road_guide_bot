import asyncio
import logging
import math
import os
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

# HTTP клиенты
_http_timeout = httpx.Timeout(25.0, connect=15.0)
geocoder_client = httpx.AsyncClient(timeout=_http_timeout)
ors_client = httpx.AsyncClient(timeout=_http_timeout)

# Логирование
logging.basicConfig(level=os.getenv("LOGLEVEL", "INFO"))
log = logging.getLogger("route-api")

app = FastAPI(title="Route Text API (Yandex Geocoder + ORS)", version="1.1.0")

# -------------------- Утилиты форматирования/геометрии --------------------


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def _interp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def sample_points_along(
    coords_lonlat: List[List[float]], interval_m: float, max_points: int = 10
) -> List[Tuple[float, float]]:
    """
    coords_lonlat: [[lon,lat], ...] от ORS
    Возвращает точки (lat, lon) через каждые interval_m, не включая концы.
    """
    if len(coords_lonlat) < 2:
        return []
    # накопим длины по сегментам
    seg_len: List[float] = []
    total = 0.0
    for i in range(len(coords_lonlat) - 1):
        lon1, lat1 = coords_lonlat[i]
        lon2, lat2 = coords_lonlat[i + 1]
        d = haversine_m(lat1, lon1, lat2, lon2)
        seg_len.append(d)
        total += d
    if total < interval_m:
        return []

    targets = []
    k = 1
    while k * interval_m < total and len(targets) < max_points:
        targets.append(k * interval_m)
        k += 1

    pts: List[Tuple[float, float]] = []
    acc = 0.0
    seg_idx = 0
    for tdist in targets:
        # идем вперёд до нужного сегмента
        while seg_idx < len(seg_len) and acc + seg_len[seg_idx] < tdist:
            acc += seg_len[seg_idx]
            seg_idx += 1
        if seg_idx >= len(seg_len):
            break
        # интерполяция внутри сегмента
        remain = tdist - acc
        frac = 0.0 if seg_len[seg_idx] == 0 else (remain / seg_len[seg_idx])
        lon1, lat1 = coords_lonlat[seg_idx]
        lon2, lat2 = coords_lonlat[seg_idx + 1]
        lat = _interp(lat1, lat2, frac)
        lon = _interp(lon1, lon2, frac)
        pts.append((round6(lat), round6(lon)))
    return pts


def fmt_distance_m(m: float) -> str:
    if m < 950:
        return f"{int(round(m))} м"
    return f"{m/1000:.1f} км".replace(".", ",")


def fmt_duration_s(s: float) -> str:
    s = int(round(s))
    h = s // 3600
    m = (s % 3600) // 60
    if h and m:
        return f"{h} ч {m} мин"
    if h:
        return f"{h} ч"
    if m:
        return f"{m} мин"
    return f"{s} с"


def round6(x: float) -> float:
    return float(f"{x:.6f}")


# -------------------- Геокодер Яндекс --------------------


async def geocode_forward(address: str) -> Tuple[float, float]:
    """Адрес -> (lat, lon)"""
    params = {
        "apikey": YANDEX_GEOCODER_API_KEY,
        "geocode": address,
        "lang": "ru_RU",
        "results": 1,
        "format": "json",
    }
    r = await geocoder_client.get(YANDEX_GEOCODER_URL, params=params)
    if r.status_code != 200:
        _msg = safe_http_error_message(r)
        raise HTTPException(r.status_code, f"Geocoder forward error: {_msg}")

    data = r.json()
    # классический ответ v1
    try:
        member = data["response"]["GeoObjectCollection"]["featureMember"][0][
            "GeoObject"
        ]
        pos = member["Point"]["pos"]  # "lon lat"
        lon_str, lat_str = pos.split()
        return float(lat_str), float(lon_str)
    except Exception:
        pass

    # альтернативные формы
    try:
        feat = data["features"][0]
        lon, lat = feat["geometry"]["coordinates"]
        return float(lat), float(lon)
    except Exception as e:
        raise HTTPException(
            422, f"Не удалось геокодировать адрес: {address!r}. Детали: {e}"
        )


_rev_sem = asyncio.Semaphore(REV_GEOCODER_CONCURRENCY)


async def geocode_reverse(
    lat: float, lon: float, kind: Optional[str] = None
) -> Dict[str, str]:
    """(lat, lon) -> компоненты адреса. Используется для locality (город/посёлок) и, при желании, улицы."""
    params = {
        "apikey": YANDEX_GEOCODER_API_KEY,
        "geocode": f"{lat},{lon}",
        "sco": "latlong",  # уточняем порядок lat,lon
        "lang": "ru_RU",
        "results": 1,
        "format": "json",
    }
    if kind:
        params["kind"] = kind

    async with _rev_sem:
        r = await geocoder_client.get(YANDEX_GEOCODER_URL, params=params)

    if r.status_code != 200:
        return {}

    data = r.json()
    try:
        member = data["response"]["GeoObjectCollection"]["featureMember"][0][
            "GeoObject"
        ]
        addr = member["metaDataProperty"]["GeocoderMetaData"]["Address"]
        comps = {c["kind"]: c["name"] for c in addr.get("Components", [])}
        name = member.get("name")
        full_text = addr.get("formatted")
        out = {"name": name, "full": full_text}
        out.update(comps)
        return out
    except Exception:
        pass

    try:
        feat = data["features"][0]
        props = feat.get("properties", {})
        comps_list = props.get("Components", []) or props.get("Address", {}).get(
            "Components", []
        )
        comps = {
            c.get("kind"): c.get("name")
            for c in comps_list
            if c.get("kind") and c.get("name")
        }
        name = props.get("name")
        descr = props.get("description")
        out = {"name": name, "full": descr}
        out.update(comps)
        return out
    except Exception:
        return {}


def safe_http_error_message(r: httpx.Response) -> str:
    try:
        j = r.json()
        return j.get("message") or str(j)[:300]
    except Exception:
        return r.text[:300]


# -------------------- OpenRouteService --------------------


async def ors_route(
    a_lat: float, a_lon: float, b_lat: float, b_lon: float, opt: OptionsIn
) -> dict:
    """Запрос маршрута: авто, ru-инструкции, метры/секунды, GeoJSON-ответ."""
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    body = {
        "coordinates": [[a_lon, a_lat], [b_lon, b_lat]],  # ORS: [lon, lat]
        "language": opt.language,
        "units": "m",
        "instructions": True,
    }
    if opt.avoid_tolls:
        body["options"] = {"avoid_features": ["tollways"]}

    r = await ors_client.post(ORS_DIRECTIONS_URL, headers=headers, json=body)
    if r.status_code != 200:
        raise HTTPException(
            502, f"ORS HTTP {r.status_code}: {safe_http_error_message(r)}"
        )
    return r.json()


def ors_extract_steps(
    data: dict,
) -> Tuple[List[StepOut], float, float, List[List[float]], List[Tuple[int, int]]]:
    """
    Возвращает:
      steps: список шагов,
      total_m / total_s: итоги,
      coords: геометрия маршрута [[lon,lat], ...],
      bounds: для каждого шага (i0, i1) индексы в coords.
    """
    features = data.get("features") or []
    if not features:
        raise HTTPException(422, "ORS: маршрут не найден (пустой features)")
    feat = features[0]
    props = feat.get("properties", {}) or {}
    summary = props.get("summary", {}) or {}
    total_m = float(summary.get("distance", 0.0))
    total_s = float(summary.get("duration", 0.0))

    coords = (feat.get("geometry") or {}).get("coordinates") or []  # [[lon,lat],...]

    out: List[StepOut] = []
    bounds: List[Tuple[int, int]] = []
    idx = 0
    for seg in props.get("segments", []) or []:
        for st in seg.get("steps", []) or []:
            wp = st.get("way_points", [0, 0])
            i0, i1 = int(wp[0]), int(wp[1])
            lon, lat = coords[i0]
            out.append(
                StepOut(
                    idx=idx,
                    start_lat=round6(float(lat)),
                    start_lon=round6(float(lon)),
                    distance_m=int(round(float(st.get("distance", 0)))),
                    duration_s=int(round(float(st.get("duration", 0)))),
                    instruction=st.get("instruction"),
                    street=(st.get("name") or None),
                    locality=None,
                )
            )
            bounds.append((i0, i1))
            idx += 1

    return out, total_m, total_s, coords, bounds


# ------- Аннотация промежуточных населённых пунктов на длинных шагах -------


async def annotate_intermediate_localities(
    steps: List[StepOut],
    step_bounds: List[Tuple[int, int]],
    coords: List[List[float]],
    *,
    min_step_m: int = 5000,
    sample_interval_m: int = 5000,
) -> None:
    """
    Для шагов длиной > min_step_m берём точки через sample_interval_m по геометрии шага,
    делаем reverse-геокод (kind=locality), собираем уникальные населённые пункты.
    """
    sample_tasks = []
    sample_meta: List[Tuple[int, float, float]] = []  # (step_idx, lat, lon)

    for i, s in enumerate(steps):
        if s.distance_m <= min_step_m:
            continue
        i0, i1 = step_bounds[i]
        sub = coords[i0 : i1 + 1]
        pts = sample_points_along(sub, interval_m=sample_interval_m, max_points=10)
        for lat, lon in pts:
            sample_meta.append((i, lat, lon))
            sample_tasks.append(geocode_reverse(lat, lon, kind="locality"))

    if not sample_tasks:
        return

    results = await asyncio.gather(*sample_tasks, return_exceptions=True)

    # Сгруппировать по шагам, оставить уникальные названия (и не совпадающие с основным locality шага)
    by_step: Dict[int, List[ViaLocality]] = {}
    for (i, lat, lon), res in zip(sample_meta, results):
        if isinstance(res, Exception) or not isinstance(res, dict):
            continue
        name = res.get("locality") or res.get("province")
        if not name:
            continue
        if i not in by_step:
            by_step[i] = []
        # не дублируем подряд одинаковые
        if not by_step[i] or by_step[i][-1].name != name:
            by_step[i].append(ViaLocality(name=name, lat=round6(lat), lon=round6(lon)))

    for i, s in enumerate(steps):
        vias = by_step.get(i, [])
        # убрать те, что совпадают с основным locality шага
        if s.locality:
            vias = [v for v in vias if v.name != s.locality]
        s.via_localities = vias or None


# -------------------- Обогащение и вывод --------------------


async def enrich_localities_with_yandex(steps: List[StepOut]) -> None:
    """Для каждого шага подтягиваем locality через обратный геокодер Яндекса."""
    tasks = []
    for s in steps:
        lat, lon = s.start_lat, s.start_lon
        if lat == 0.0 and lon == 0.0:
            tasks.append(asyncio.sleep(0, result={}))
        else:
            tasks.append(geocode_reverse(lat, lon, kind="locality"))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for s, res in zip(steps, results):
        if isinstance(res, Exception) or not isinstance(res, dict):
            continue
        s.locality = res.get("locality") or res.get("province") or None


def build_markdown(
    a_label: str,
    a_lat: float,
    a_lon: float,
    b_label: str,
    b_lat: float,
    b_lon: float,
    steps: List[StepOut],
    total_m: float,
    total_s: float,
) -> str:
    md = []
    md.append("# Маршрут A → B\n")
    md.append(
        f"**A:** {a_label} ({a_lat:.6f}, {a_lon:.6f})  \n**B:** {b_label} ({b_lat:.6f}, {b_lon:.6f})\n"
    )
    md.append(f"**Итого:** {fmt_distance_m(total_m)} • {fmt_duration_s(total_s)}\n")

    # Группировка по нас. пунктам
    md.append("## По населённым пунктам\n")
    cur_loc = None
    buf: List[StepOut] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        loc = cur_loc or "Между населёнными пунктами"
        md.append(f"### {loc}\n")
        for s in buf:
            instr = s.instruction or ""
            street = s.street or "без названия"
            md.append(
                f"- {instr} — **{street}** — {fmt_distance_m(s.distance_m)} • {fmt_duration_s(s.duration_s)}  \n"
                f"  координаты: ({s.start_lat:.6f}, {s.start_lon:.6f})"
            )
            if s.via_localities:
                for v in s.via_localities:
                    md.append(f"  - через: **{v.name}** ({v.lat:.6f}, {v.lon:.6f})")
        md.append("")
        buf = []

    for s in steps:
        if s.locality != cur_loc:
            flush()
            cur_loc = s.locality
        buf.append(s)
    flush()

    md.append("## Ключевые точки\n")
    for s in steps:
        md.append(
            f"- Шаг {s.idx+1}: ({s.start_lat:.6f}, {s.start_lon:.6f}) — {s.street or 'улица не определена'}"
        )

    return "\n".join(md)


async def ensure_coords(p: PointIn) -> Tuple[float, float, str]:
    if p.lat is not None and p.lon is not None:
        return float(p.lat), float(p.lon), f"{p.lat:.6f}, {p.lon:.6f}"
    lat, lon = await geocode_forward(p.address)
    return lat, lon, p.address


# -------------------- Грейсфул шатдаун --------------------


@app.on_event("shutdown")
async def _shutdown():
    await geocoder_client.aclose()
    await ors_client.aclose()
