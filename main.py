"""気象庁データ取得 + dbt ビルド + メタデータ生成パイプライン。

非公式 JSON API からマスタ（観測所一覧・地域コード）と府県予報区ごとの短期天気予報を
取得し、地震月報（カタログ編）の震源データ（96 バイト固定長）を取得・整形して、DuckDB が
読みやすい NDJSON に整形して .fdl/ に保存してから dbt を実行する。
"""

import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from dbt.cli.main import dbtRunner

AMEDAS_TABLE_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"

# 地震月報（カタログ編）の震源データ。年別 ZIP（96 バイト固定長レコード）で配布される。
# https://www.data.jma.go.jp/eqev/data/bulletin/hypo.html
HYPOCENTER_BASE_URL = "https://www.data.jma.go.jp/eqev/data/bulletin/data/hypo"

# 取り込む年（直近の確定済み年から 5 年）。カタログは確定までに数年のラグがあり、
# 現時点の最新確定年は 2023 年。年を追加すれば取り込み範囲を拡張できる。
HYPOCENTER_YEARS = [2019, 2020, 2021, 2022, 2023]

# 府県予報区ごとの天気予報 JSON。area.json の offices（府県予報区）コードを URL に埋める。
# 各ファイルの先頭要素が短期予報（今日・明日・明後日）で、その timeSeries[0] が
# 一次細分区域（class10）別の天気・風・波。ビルド時点の最新発表を 1 スナップショット取得する。
# https://www.jma.go.jp/bosai/forecast/
FORECAST_BASE_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast"

# 気象庁サーバーへの配慮。連続リクエストの最小間隔（秒）と識別用 User-Agent。
# 時間をかけてでもゆったりアクセスする方針。obsdl 等のバッチ取得でも同じ間隔を使う。
REQUEST_INTERVAL_SEC = 3.0
USER_AGENT = "queria-dataset-jma/0.1 (+https://github.com/flo8s/dataset-jma)"

_last_request_at = 0.0

FDL_DIR = Path(".fdl")
STATIONS_PATH = FDL_DIR / "jma_stations.ndjson"
AREAS_PATH = FDL_DIR / "jma_areas.ndjson"
HYPOCENTERS_PATH = FDL_DIR / "jma_hypocenters.ndjson"
FORECASTS_PATH = FDL_DIR / "jma_forecasts.ndjson"

# 気象官署（管区・地方気象台や測候所相当）の観測所種別。
# amedas のうち type A/B が気象官署に相当する。
OFFICE_TYPES = {"A", "B"}

# area.json の階層キー → level ラベル
AREA_LEVELS = {
    "centers": "center",
    "offices": "office",
    "class10s": "class10",
    "class15s": "class15",
    "class20s": "class20",
}

# 震源レコードのレコード種別ヘッダ（欄 01）。
HYPOCENTER_RECORD_TYPES = {
    "J": "気象庁",
    "U": "USGS",
    "I": "国際機関",
}

# 0 未満のマグニチュードの特殊表記（欄 53-54 の先頭文字）。
# A0=-1.0, A9=-1.9, B0=-2.0, C0=-3.0 のように 10 の位を表す。
MAG_NEGATIVE_PREFIX = {"A": -1, "B": -2, "C": -3}


def main() -> None:
    FDL_DIR.mkdir(exist_ok=True)
    _build_stations()
    _build_areas()
    _build_hypocenters()
    _build_forecasts()

    dbt = dbtRunner()

    result = dbt.invoke(["deps"])
    if not result.success:
        raise SystemExit("dbt deps failed")

    result = dbt.invoke(["run"])
    if not result.success:
        raise SystemExit("dbt run failed")

    result = dbt.invoke(["docs", "generate"])
    if not result.success:
        raise SystemExit("dbt docs generate failed")


def _throttle() -> None:
    """直前のリクエストから最低 REQUEST_INTERVAL_SEC 空ける。"""
    global _last_request_at
    wait = REQUEST_INTERVAL_SEC - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _fetch_json(url: str):
    """間隔を空けて JSON を取得する（気象庁サーバーへの配慮）。"""
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _fetch_bytes(url: str) -> bytes:
    """間隔を空けてバイト列を取得する（気象庁サーバーへの配慮）。"""
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def _dms_to_deg(dms: list[float]) -> float:
    """[度, 分] 形式の座標を十進度に変換する。"""
    return round(dms[0] + dms[1] / 60, 6)


def _build_stations() -> None:
    """amedastable.json を観測所マスタの NDJSON に整形する。"""
    table = _fetch_json(AMEDAS_TABLE_URL)
    with STATIONS_PATH.open("w", encoding="utf-8") as f:
        for station_id, v in table.items():
            station_type = v.get("type")
            row = {
                "station_id": station_id,
                "name": v.get("kjName"),
                "name_kana": v.get("knName"),
                "name_en": v.get("enName"),
                "lat": _dms_to_deg(v["lat"]),
                "lon": _dms_to_deg(v["lon"]),
                "elevation": v.get("alt"),
                "station_type": station_type,
                "is_office": station_type in OFFICE_TYPES,
                "elems": v.get("elems"),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"  jma_stations.ndjson: {len(table)} stations")


def _build_areas() -> None:
    """area.json の階層を level 付きでフラット化した NDJSON に整形する。"""
    area = _fetch_json(AREA_URL)
    count = 0
    with AREAS_PATH.open("w", encoding="utf-8") as f:
        for key, level in AREA_LEVELS.items():
            for area_code, v in area.get(key, {}).items():
                row = {
                    "area_code": area_code,
                    "level": level,
                    "name": v.get("name"),
                    "name_en": v.get("enName"),
                    "name_kana": v.get("kana"),
                    "office_name": v.get("officeName"),
                    "parent_code": v.get("parent"),
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
    print(f"  jma_areas.ndjson: {count} areas")


def _hypo_int(field: str):
    """符号付き整数欄をパースする（国際機関の震源は緯度経度が負になり得る）。"""
    s = field.strip()
    if s in ("", "-"):
        return None
    digits = re.sub(r"[^0-9]", "", s)
    if digits == "":
        return None
    value = int(digits)
    return -value if "-" in s else value


def _hypo_coord(deg_field: str, min_field: str):
    """度欄（I3/I4）と分欄（F4.2、値÷100）から十進度を組み立てる。"""
    deg = _hypo_int(deg_field)
    if deg is None:
        return None
    minute_raw = min_field.strip()
    minute = int(minute_raw) / 100 if minute_raw not in ("", "-") else 0.0
    if deg < 0:
        return round(deg - minute / 60, 6)
    return round(deg + minute / 60, 6)


def _hypo_magnitude(field: str):
    """マグニチュード欄（F2.1、値÷10）をパースする。0 未満は A0/B0/C0 表記。"""
    if field.strip() == "":
        return None
    head = field[0]
    if head in MAG_NEGATIVE_PREFIX:
        ones = field[1]
        if not ones.isdigit():
            return None
        return round((MAG_NEGATIVE_PREFIX[head] * 10 - int(ones)) / 10, 1)
    try:
        return round(int(field) / 10, 1)
    except ValueError:
        return None


def _hypo_depth(field: str):
    """深さ欄（5 桁）をパースする。末尾 2 桁が空白なら整数 km（固定/刻み）、
    そうでなければ F5.2（値÷100、深さフリー）。"""
    if field.strip() == "":
        return None
    if field[3:5].strip() == "":
        head = field[0:3].strip()
        if head in ("", "-"):
            return None
        return float(int(head))
    try:
        return round(int(field.strip()) / 100, 2)
    except ValueError:
        return None


def _parse_hypocenter(line: str) -> dict | None:
    """震源レコード（96 バイト固定長）を 1 件分の dict にパースする。"""
    record = line.rstrip("\n")
    if record.strip() == "":
        return None
    if len(record) < 96:
        record = record.ljust(96)

    year = record[1:5].strip()
    month = record[5:7].strip()
    day = record[7:9].strip()
    hour = record[9:11].strip()
    minute = record[11:13].strip()
    if not (year and month and day and hour and minute):
        return None
    second_raw = record[13:17].strip()
    second = int(second_raw) / 100 if second_raw != "" else 0.0
    origin_time = (
        f"{int(year):04d}-{int(month):02d}-{int(day):02d} "
        f"{int(hour):02d}:{int(minute):02d}:{second:05.2f}"
    )

    station_count_raw = record[92:95].strip()
    return {
        "record_type": record[0],
        "origin_time": origin_time,
        "latitude": _hypo_coord(record[21:24], record[24:28]),
        "longitude": _hypo_coord(record[32:36], record[36:40]),
        "depth_km": _hypo_depth(record[44:49]),
        "magnitude": _hypo_magnitude(record[52:54]),
        "magnitude_type": record[54].strip() or None,
        "magnitude2": _hypo_magnitude(record[55:57]),
        "magnitude2_type": record[57].strip() or None,
        "subtype_code": record[60].strip() or None,
        "max_intensity_code": record[61].strip() or None,
        "region": record[68:92].strip() or None,
        "station_count": int(station_count_raw) if station_count_raw else None,
        "hypocenter_flag": record[95].strip() or None,
    }


def _build_hypocenters() -> None:
    """地震月報（カタログ編）の年別震源 ZIP を取得し NDJSON に整形する。"""
    count = 0
    with HYPOCENTERS_PATH.open("w", encoding="utf-8") as f:
        for year in HYPOCENTER_YEARS:
            data = _fetch_bytes(f"{HYPOCENTER_BASE_URL}/h{year}.zip")
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                members = zf.namelist()
                year_count = 0
                for member in members:
                    with zf.open(member) as fh:
                        text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
                        for line in text:
                            row = _parse_hypocenter(line)
                            if row is None:
                                continue
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")
                            year_count += 1
                count += year_count
                print(f"    h{year}: {year_count} hypocenters")
    print(f"  jma_hypocenters.ndjson: {count} hypocenters")


def _forecast_weather_rows(office_code: str, data: list) -> list[dict]:
    """府県予報区の予報 JSON から短期天気予報（class10 別）の行を取り出す。

    先頭要素が短期予報で、その timeSeries[0] が天気・風・波の時系列。timeSeries[0]
    の各エリア（一次細分区域）× timeDefines（今日・明日・明後日）で 1 行を作る。
    波（waves）は内陸の区域には無いので欠損を許容する。
    """
    if not data:
        return []
    short_term = data[0]
    report_datetime = short_term.get("reportDatetime")
    series = short_term.get("timeSeries") or []
    if not series:
        return []
    weather = series[0]
    time_defines = weather.get("timeDefines") or []
    rows = []
    for area in weather.get("areas") or []:
        area_info = area.get("area") or {}
        area_code = area_info.get("code")
        area_name = area_info.get("name")
        codes = area.get("weatherCodes") or []
        texts = area.get("weathers") or []
        winds = area.get("winds") or []
        waves = area.get("waves") or []
        for i, forecast_datetime in enumerate(time_defines):
            rows.append(
                {
                    "office_code": office_code,
                    "report_datetime": report_datetime,
                    "area_code": area_code,
                    "area_name": area_name,
                    "forecast_datetime": forecast_datetime,
                    "weather_code": codes[i] if i < len(codes) else None,
                    "weather": texts[i] if i < len(texts) else None,
                    "wind": winds[i] if i < len(winds) else None,
                    "wave": waves[i] if i < len(waves) else None,
                }
            )
    return rows


def _build_forecasts() -> None:
    """府県予報区ごとの短期天気予報を取得し、class10 区域×対象日時の NDJSON に整形する。

    予報対象の区域は area.json の offices（府県予報区）。区域コードは area.json の
    class10 と一致し mart_jma_areas と結合できる。ビルド時点の最新発表を取得する。
    """
    area = _fetch_json(AREA_URL)
    office_codes = sorted(area.get("offices", {}).keys())
    count = 0
    offices = 0
    with FORECASTS_PATH.open("w", encoding="utf-8") as f:
        for office_code in office_codes:
            url = f"{FORECAST_BASE_URL}/{office_code}.json"
            try:
                data = _fetch_json(url)
            except urllib.error.HTTPError as exc:
                # 予報を提供しない区域（例: 別区域に統合済み）は 404 になり得る。
                print(f"    forecast {office_code}: skip ({exc.code})")
                continue
            rows = _forecast_weather_rows(office_code, data)
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += len(rows)
            offices += 1
    print(f"  jma_forecasts.ndjson: {count} rows / {offices} offices")


if __name__ == "__main__":
    main()
