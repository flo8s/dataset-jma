{{ config(materialized='view') }}

select
    origin_time,
    latitude,
    longitude,
    depth_km,
    magnitude,
    magnitude_type,
    magnitude2,
    magnitude2_type,
    region,
    case record_type
        when 'J' then '気象庁'
        when 'U' then 'USGS'
        when 'I' then '国際機関'
    end as record_source,
    record_type,
    subtype_code,
    case subtype_code
        when '1' then '通常地震'
        when '2' then '他機関依存'
        when '3' then '人工地震'
        when '4' then '噴火に伴う地震動等'
        when '5' then '低周波イベント'
    end as subtype,
    max_intensity_code,
    case max_intensity_code
        when '1' then '震度1'
        when '2' then '震度2'
        when '3' then '震度3'
        when '4' then '震度4'
        when '5' then '震度5'
        when '6' then '震度6'
        when '7' then '震度7'
        when 'A' then '震度5弱'
        when 'B' then '震度5強'
        when 'C' then '震度6弱'
        when 'D' then '震度6強'
    end as max_intensity,
    station_count,
    hypocenter_flag
from {{ ref('raw_jma_hypocenters') }}
