{# 気象庁の地域コード（area.json を level 付きでフラット化したもの）
   元データ: https://www.jma.go.jp/bosai/common/const/area.json
   main.py が centers/offices/class10s/class15s/class20s を縦持ちにして .fdl/jma_areas.ndjson に保存 #}

{{
    config(
        materialized='table'
    )
}}

select *
from read_json(
    '.fdl/jma_areas.ndjson',
    format='newline_delimited',
    columns={
        'area_code': 'VARCHAR',
        'level': 'VARCHAR',
        'name': 'VARCHAR',
        'name_en': 'VARCHAR',
        'name_kana': 'VARCHAR',
        'office_name': 'VARCHAR',
        'parent_code': 'VARCHAR'
    }
)
