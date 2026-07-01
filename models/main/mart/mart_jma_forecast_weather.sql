{{ config(materialized='view') }}

select
    office_code,
    report_datetime::timestamptz as report_datetime,
    area_code,
    area_name,
    forecast_datetime::timestamptz as forecast_datetime,
    weather_code,
    weather,
    wind,
    wave
from {{ ref('raw_jma_forecasts') }}
