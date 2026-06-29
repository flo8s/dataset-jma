{{ config(materialized='view') }}

select
    station_id,
    month,
    day,
    temp_avg_c,
    temp_max_c,
    temp_min_c,
    sunshine_hours,
    precipitation_mm,
    snow_depth_cm
from {{ ref('raw_jma_normals_daily') }}
