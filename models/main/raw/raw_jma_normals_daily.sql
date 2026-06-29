{# アメダス日別平年値（normal_amedas_daily.zip を NDJSON に整形したもの）
   元データ: https://www.data.jma.go.jp/stats/data/mdrr/normal/index.html
   main.py が要素番号 0500/0600/0700/3500/4000/6200 を観測所×月日に展開し
   実単位へスケールして .fdl/jma_normals_daily.ndjson に保存する #}

{{
    config(
        materialized='table'
    )
}}

select *
from read_json(
    '.fdl/jma_normals_daily.ndjson',
    format='newline_delimited',
    columns={
        'station_id': 'VARCHAR',
        'month': 'INTEGER',
        'day': 'INTEGER',
        'temp_avg_c': 'DOUBLE',
        'temp_max_c': 'DOUBLE',
        'temp_min_c': 'DOUBLE',
        'sunshine_hours': 'DOUBLE',
        'precipitation_mm': 'DOUBLE',
        'snow_depth_cm': 'INTEGER'
    }
)
