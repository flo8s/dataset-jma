"""気象庁データ取得 + dbt ビルド + メタデータ生成パイプライン。

非公式 JSON API からマスタ（観測所一覧・地域コード）を取得し、平年値ダウンロードの
アメダス日別平年値（1991〜2020 年）を取得・整形して、DuckDB が読みやすい NDJSON に
整形して .fdl/ に保存してから dbt を実行する。
"""

import calendar
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

from dbt.cli.main import dbtRunner

AMEDAS_TABLE_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"

# アメダス（地域気象観測）日別平年値（統計期間：1991〜2020 年、2020 年平年値）。
# 観測所別の ZIP（Shift-JIS の固定長 CSV）で配布される。
# https://www.data.jma.go.jp/stats/data/mdrr/normal/index.html
NORMALS_DAILY_URL = (
    "https://www.data.jma.go.jp/stats/data/mdrr/normal/2020/data/normal_amedas_daily.zip"
)

# 気象庁サーバーへの配慮。連続リクエストの最小間隔（秒）と識別用 User-Agent。
# 時間をかけてでもゆったりアクセスする方針。obsdl 等のバッチ取得でも同じ間隔を使う。
REQUEST_INTERVAL_SEC = 3.0
USER_AGENT = "queria-dataset-jma/0.1 (+https://github.com/flo8s/dataset-jma)"

_last_request_at = 0.0

FDL_DIR = Path(".fdl")
STATIONS_PATH = FDL_DIR / "jma_stations.ndjson"
AREAS_PATH = FDL_DIR / "jma_areas.ndjson"
NORMALS_DAILY_PATH = FDL_DIR / "jma_normals_daily.ndjson"

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

# 日別平年値ファイルから取り込む要素番号 → (出力カラム名, スケール係数)。
# 値はスケール係数で割って実単位に直す（係数 1 はそのまま）。
# 気温は 0.1℃・日照時間は 0.1 時間・降水量は 0.1mm・積雪の深さは 1cm。
# 標準偏差・階級区分・時刻別気温も同ファイルに含まれるが、本テーブルでは
# 日別気候値の中核 6 要素に絞る。
NORMALS_DAILY_ELEMENTS = {
    "0500": ("temp_avg_c", 10.0),
    "0600": ("temp_max_c", 10.0),
    "0700": ("temp_min_c", 10.0),
    "3500": ("sunshine_hours", 10.0),
    "4000": ("precipitation_mm", 10.0),
    "6200": ("snow_depth_cm", 1.0),
}

# 観測値のリマーク（RMK）。8=正常値のみ採用し、0=統計値なしは欠損とする。
NORMALS_VALID_RMK = "8"


def main() -> None:
    FDL_DIR.mkdir(exist_ok=True)
    _build_stations()
    _build_areas()
    _build_normals_daily()

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


def _days_in_month(month: int) -> int:
    """平年値の収録日数。2 月は閏日（29 日）まで含む。"""
    return 29 if month == 2 else calendar.monthrange(2001, month)[1]


def _normals_value(raw: str, rmk: str, scale: float):
    """日別平年値の値欄をパースする。RMK=8（正常値）のみ採用する。
    係数 1.0 の要素（積雪の深さ）は整数 cm、それ以外は実単位に直して返す。"""
    if rmk != NORMALS_VALID_RMK:
        return None
    value = raw.strip()
    if value in ("", "-"):
        return None
    number = int(value)
    if scale == 1.0:
        return number
    return round(number / scale, 1)


def _parse_normals_station(text: io.TextIOWrapper) -> tuple[str | None, dict]:
    """1 観測所分の日別平年値 CSV を {(要素番号, 月): [(値, RMK), ...]} に整形する。

    日別平年値ファイルはカンマ区切りの固定長で、1 行が「要素番号×月」に対応し、
    その月の 1〜31 日の値と RMK が並ぶ（平年値種別 25）。
    """
    station_id = None
    by_element_month: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for line in text:
        fields = [c.strip() for c in line.rstrip("\n").split(",")]
        if len(fields) < 9:
            continue
        station_id = fields[1]
        element_code = fields[2]
        if element_code not in NORMALS_DAILY_ELEMENTS:
            continue
        month = int(fields[6])
        # fields[7] 以降は (1 日値, RMK, 2 日値, RMK, ...) の並び。
        days = []
        for day_index in range(31):
            value_pos = 7 + day_index * 2
            rmk_pos = 8 + day_index * 2
            if rmk_pos < len(fields):
                days.append((fields[value_pos], fields[rmk_pos]))
        by_element_month[(element_code, month)] = days
    return station_id, by_element_month


def _build_normals_daily() -> None:
    """アメダス日別平年値の ZIP を取得し、観測所×月日の NDJSON に整形する。"""
    archive = _fetch_bytes(NORMALS_DAILY_URL)
    count = 0
    stations = 0
    with (
        zipfile.ZipFile(io.BytesIO(archive)) as zf,
        NORMALS_DAILY_PATH.open("w", encoding="utf-8") as out,
    ):
        members = sorted(m for m in zf.namelist() if m.endswith(".csv"))
        for member in members:
            with zf.open(member) as fh:
                text = io.TextIOWrapper(fh, encoding="shift_jis", errors="replace")
                station_id, by_element_month = _parse_normals_station(text)
            if station_id is None:
                continue
            stations += 1
            for month in range(1, 13):
                for day in range(1, _days_in_month(month) + 1):
                    row = {"station_id": station_id, "month": month, "day": day}
                    for element_code, (column, scale) in NORMALS_DAILY_ELEMENTS.items():
                        days = by_element_month.get((element_code, month))
                        value = None
                        if days is not None and day - 1 < len(days):
                            raw, rmk = days[day - 1]
                            value = _normals_value(raw, rmk, scale)
                        row[column] = value
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1
    print(f"  jma_normals_daily.ndjson: {count} rows / {stations} stations")


if __name__ == "__main__":
    main()
