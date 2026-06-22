{{ config(materialized='view') }}

select
    area_code,
    level,
    name,
    name_en,
    name_kana,
    office_name,
    parent_code
from {{ ref('raw_jma_areas') }}
