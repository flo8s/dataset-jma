{# 気象庁アメダス観測所一覧（amedastable.json を NDJSON に整形したもの）
   元データ: https://www.jma.go.jp/bosai/amedas/const/amedastable.json
   main.py が緯度経度を十進度化し .fdl/jma_stations.ndjson に保存 #}

{{
    config(
        materialized='table'
    )
}}

select *
from read_json(
    '.fdl/jma_stations.ndjson',
    format='newline_delimited',
    columns={
        'station_id': 'VARCHAR',
        'name': 'VARCHAR',
        'name_kana': 'VARCHAR',
        'name_en': 'VARCHAR',
        'lat': 'DOUBLE',
        'lon': 'DOUBLE',
        'elevation': 'INTEGER',
        'station_type': 'VARCHAR',
        'is_office': 'BOOLEAN',
        'elems': 'VARCHAR'
    }
)
