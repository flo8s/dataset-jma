{# 気象庁 地震月報（カタログ編）の震源データ（96 バイト固定長を整形したもの）
   元データ: https://www.data.jma.go.jp/eqev/data/bulletin/hypo.html
   main.py が年別 ZIP を取得し緯度経度・深さ・マグニチュードを十進化して
   .fdl/jma_hypocenters.ndjson に保存 #}

{{
    config(
        materialized='table'
    )
}}

select *
from read_json(
    '.fdl/jma_hypocenters.ndjson',
    format='newline_delimited',
    columns={
        'record_type': 'VARCHAR',
        'origin_time': 'TIMESTAMP',
        'latitude': 'DOUBLE',
        'longitude': 'DOUBLE',
        'depth_km': 'DOUBLE',
        'magnitude': 'DOUBLE',
        'magnitude_type': 'VARCHAR',
        'magnitude2': 'DOUBLE',
        'magnitude2_type': 'VARCHAR',
        'subtype_code': 'VARCHAR',
        'max_intensity_code': 'VARCHAR',
        'region': 'VARCHAR',
        'station_count': 'INTEGER',
        'hypocenter_flag': 'VARCHAR'
    }
)
