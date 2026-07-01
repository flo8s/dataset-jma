{# 府県予報区ごとの短期天気予報（forecast JSON を class10 区域×対象日時に展開したもの）
   元データ: https://www.jma.go.jp/bosai/forecast/
   main.py が offices ごとの予報の先頭要素・timeSeries[0]（天気・風・波）を
   一次細分区域×timeDefines に展開して .fdl/jma_forecasts.ndjson に保存する #}

{{
    config(
        materialized='table'
    )
}}

select *
from read_json(
    '.fdl/jma_forecasts.ndjson',
    format='newline_delimited',
    columns={
        'office_code': 'VARCHAR',
        'report_datetime': 'VARCHAR',
        'area_code': 'VARCHAR',
        'area_name': 'VARCHAR',
        'forecast_datetime': 'VARCHAR',
        'weather_code': 'VARCHAR',
        'weather': 'VARCHAR',
        'wind': 'VARCHAR',
        'wave': 'VARCHAR'
    }
)
