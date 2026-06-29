## データ出典

[気象庁](https://www.jma.go.jp/)が公開している気象データです。観測所一覧（アメダス）・予報区の地域コードと、アメダス観測所の日別平年値（1991〜2020年）を収録しています。

観測所一覧・地域コードは非公式の JSON 配信（気象庁サイトが内部利用しているエンドポイント）を、日別平年値は平年値ダウンロードの配布ファイルを出典として利用しています。

- 観測所一覧: https://www.jma.go.jp/bosai/amedas/const/amedastable.json
- 地域コード: https://www.jma.go.jp/bosai/common/const/area.json
- 日別平年値: https://www.data.jma.go.jp/stats/data/mdrr/normal/index.html （normal_amedas_daily）

## テーブル: mart_jma_stations

全国のアメダス観測所の一覧です。観測所の位置（緯度経度・標高）と種別を持ちます。

- station_id: 観測所ID（VARCHAR、アメダス番号5桁）
- name / name_kana / name_en: 観測所名 漢字 / カナ / 英語（VARCHAR）
- lat / lon: 緯度 / 経度（DOUBLE、十進度）
- elevation: 標高（INTEGER、メートル）
- station_type: 観測所種別（VARCHAR、A〜G。A/Bが気象官署相当）
- is_office: 気象官署フラグ（BOOLEAN、種別A/B）
- elems: 観測種目フラグ（VARCHAR、気象庁仕様の8桁文字列）

## テーブル: mart_jma_areas

気象庁の予報区の地域コードです。全国〜市区町村までの階層を level 付きで縦持ちにしています。

- area_code: 地域コード（VARCHAR）
- level: 階層（VARCHAR、center / office / class10 / class15 / class20）
- name / name_en: 地域名 / 英語（VARCHAR）
- name_kana: 地域名カナ（VARCHAR、class20のみ）
- office_name: 担当気象台名（VARCHAR、center / office のみ）
- parent_code: 親地域コード（VARCHAR、center は NULL）

## テーブル: mart_jma_normals_daily

アメダス観測所の日別平年値（統計期間1991〜2020年）です。観測所×月日ごとに、気温・日照時間・降水量・積雪の深さの30年平均を持ちます。station_id で mart_jma_stations と結合できます。観測していない要素や統計値なしの日は NULL です（2月は閏日29日まで収録）。

- station_id: 観測所ID（VARCHAR、アメダス番号5桁）
- month / day: 月 / 日（INTEGER、月1〜12・日1〜31）
- temp_avg_c: 日平均気温の平年値（DOUBLE、℃）
- temp_max_c: 日最高気温の平年値（DOUBLE、℃）
- temp_min_c: 日最低気温の平年値（DOUBLE、℃）
- sunshine_hours: 日照時間の平年値（DOUBLE、時間）
- precipitation_mm: 降水量の平年値（DOUBLE、mm）
- snow_depth_cm: 積雪の深さ（日最大）の平年値（INTEGER、cm）

### データ更新手順

main.py が気象庁の JSON（amedastable.json / area.json）と平年値ダウンロードの日別平年値 ZIP（normal_amedas_daily）を取得し、緯度経度の十進度化・地域階層のフラット化・日別平年値の観測所×月日への展開と実単位へのスケールを行って `.fdl/` に NDJSON として保存し、dbt build でテーブルを再生成する。ビルドは `bash scripts/build.sh local` で実行する。

## ライセンス

出典は気象庁。[気象庁ホームページ利用規約](https://www.jma.go.jp/jma/kishou/info/coment.html)（政府標準利用規約 第2.0版に準拠）に従う。
