{{ config(materialized='view') }}

select
    station_id,
    name,
    name_kana,
    name_en,
    lat,
    lon,
    elevation,
    station_type,
    is_office,
    elems
from {{ ref('raw_jma_stations') }}
