## データ出典

[気象庁](https://www.jma.go.jp/bosai/amedas/)が公開している気象データです。観測所一覧（アメダス）と予報区の地域コードを収録しています。

非公式の JSON 配信（気象庁サイトが内部利用しているエンドポイント）を出典として利用しています。

- 観測所一覧: https://www.jma.go.jp/bosai/amedas/const/amedastable.json
- 地域コード: https://www.jma.go.jp/bosai/common/const/area.json

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

### データ更新手順

main.py が気象庁の JSON（amedastable.json / area.json）を取得し、緯度経度の十進度化と地域階層のフラット化を行って `.fdl/` に NDJSON として保存し、dbt build でテーブルを再生成する。ビルドは `bash scripts/build.sh local` で実行する。

## ライセンス

出典は気象庁。[気象庁ホームページ利用規約](https://www.jma.go.jp/jma/kishou/info/coment.html)（政府標準利用規約 第2.0版に準拠）に従う。
