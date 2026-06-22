"""気象庁データ取得 + dbt ビルド + メタデータ生成パイプライン。

非公式 JSON API からマスタ（観測所一覧・地域コード）を取得し、
DuckDB が読みやすい NDJSON に整形して .fdl/ に保存してから dbt を実行する。
"""

import json
import time
import urllib.request
from pathlib import Path

from dbt.cli.main import dbtRunner

AMEDAS_TABLE_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"

# 気象庁サーバーへの配慮。連続リクエストの最小間隔（秒）と識別用 User-Agent。
# 時間をかけてでもゆったりアクセスする方針。obsdl 等のバッチ取得でも同じ間隔を使う。
REQUEST_INTERVAL_SEC = 3.0
USER_AGENT = "queria-dataset-jma/0.1 (+https://github.com/flo8s/dataset-jma)"

_last_request_at = 0.0

FDL_DIR = Path(".fdl")
STATIONS_PATH = FDL_DIR / "jma_stations.ndjson"
AREAS_PATH = FDL_DIR / "jma_areas.ndjson"

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


def main() -> None:
    FDL_DIR.mkdir(exist_ok=True)
    _build_stations()
    _build_areas()

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


if __name__ == "__main__":
    main()
