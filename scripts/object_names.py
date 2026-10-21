"""Display names for furniture, camera detections and dirt (English, German).

Source for the `selector` sections of strings.json and translations/*.json;
run this script after editing to write them:

    python scripts/object_names.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "narwal_local"

OBSTACLES = {  # ObstacleLabel name (lowercase): (en, de)
    "unspecified": ("Object", "Gegenstand"),
    "cable": ("Cable", "Kabel"),
    "tissue": ("Tissue", "Taschentuch"),
    "poop": ("Pet waste", "Haustierkot"),
    "liquid": ("Liquid", "Flüssigkeit"),
    "shoes": ("Shoes", "Schuhe"),
    "solid": ("Solid object", "Fester Gegenstand"),
    "socks": ("Socks", "Socken"),
    "plastic_bag": ("Plastic bag", "Plastiktüte"),
    "trash_bin": ("Trash bin", "Mülleimer"),
    "normal": ("Obstacle", "Hindernis"),
    "uncleanable": ("Uncleanable spot", "Nicht reinigbar"),
    "textiles": ("Textiles", "Textilien"),
    "not_exist": ("No longer there", "Nicht mehr vorhanden"),
    "ground_texture": ("Floor pattern", "Bodenmuster"),
    "pet": ("Pet", "Haustier"),
    "cliff": ("Drop", "Absturzkante"),
    "squatting_wc": ("Squat toilet", "Hocktoilette"),
    "chair_u_legs": ("Chair (U legs)", "Stuhl (U-Fuß)"),
    "chair_wheel": ("Office chair", "Bürostuhl"),
    "floor_mirror": ("Floor mirror", "Standspiegel"),
    "book": ("Book", "Buch"),
    "stick": ("Stick", "Stab"),
    "merge_flexible": ("Soft object", "Weicher Gegenstand"),
    "jewelry": ("Jewelry", "Schmuck"),
    "phone": ("Phone", "Handy"),
    "wallet": ("Wallet", "Geldbörse"),
    "key": ("Key", "Schlüssel"),
    "banknote": ("Banknote", "Geldschein"),
    "remote_control": ("Remote control", "Fernbedienung"),
    "glasses": ("Glasses", "Brille"),
    "watch": ("Watch", "Uhr"),
    "card": ("Card", "Karte"),
    "headphones": ("Headphones", "Kopfhörer"),
    "baby_toy": ("Baby toy", "Babyspielzeug"),
    "plant": ("Plant", "Pflanze"),
    "fitness_equipment": ("Fitness equipment", "Fitnessgerät"),
    "pet_toy": ("Pet toy", "Haustierspielzeug"),
    "dangerous_goods": ("Hazardous item", "Gefährlicher Gegenstand"),
    "decoration": ("Decoration", "Dekoration"),
    "paper_box": ("Cardboard box", "Karton"),
    "pet_cat": ("Cat", "Katze"),
    "pet_dog": ("Dog", "Hund"),
}

FURNITURE = {  # FurnitureType name (lowercase): (en, de)
    "unspecified": ("Furniture", "Möbelstück"),
    "single_bed": ("Single bed", "Einzelbett"),
    "double_bed": ("Double bed", "Doppelbett"),
    "baby_bed": ("Cot", "Babybett"),
    "dinner_table_square": ("Dining table", "Esstisch"),
    "dinner_table_round": ("Round dining table", "Runder Esstisch"),
    "tea_table_square": ("Coffee table", "Couchtisch"),
    "tea_table_round": ("Round coffee table", "Runder Couchtisch"),
    "tv_cupboard": ("TV stand", "TV-Möbel"),
    "bedside_table": ("Bedside table", "Nachttisch"),
    "locker": ("Cabinet", "Schrank"),
    "wardrobe": ("Wardrobe", "Kleiderschrank"),
    "shoe_cupboard": ("Shoe cabinet", "Schuhschrank"),
    "sofa_single": ("Armchair", "Sessel"),
    "sofa_multi": ("Sofa", "Sofa"),
    "sofa_l_shape": ("Corner sofa", "Ecksofa"),
    "sofa_lazy": ("Bean bag", "Sitzsack"),
    "chair": ("Chair", "Stuhl"),
    "bar_chair": ("Bar stool", "Barhocker"),
    "cat_toilet": ("Litter box", "Katzenklo"),
    "pet_eating_area": ("Pet feeding area", "Futterplatz"),
    "pet_house": ("Pet bed", "Haustierbett"),
    "washing_machine": ("Washing machine", "Waschmaschine"),
    "refrigerator": ("Refrigerator", "Kühlschrank"),
    "vertical_aircon": ("Air conditioner", "Klimagerät"),
    "vertical_fan": ("Fan", "Ventilator"),
    "potted_plant": ("Potted plant", "Topfpflanze"),
    "floor_mirror": ("Floor mirror", "Standspiegel"),
    "toilet": ("Toilet", "Toilette"),
    "piano": ("Piano", "Klavier"),
    "sofa_u_shape": ("U-shaped sofa", "U-Sofa"),
    "desk": ("Desk", "Schreibtisch"),
    "grand_piano": ("Grand piano", "Flügel"),
    "washbasin": ("Washbasin", "Waschbecken"),
    "cooker_hood_stove": ("Stove", "Herd"),
    "wine_cabinet": ("Wine cabinet", "Weinschrank"),
    "cat_house": ("Cat house", "Katzenhaus"),
    "dog_house": ("Dog house", "Hundehütte"),
    "round_placeholder": ("Round object", "Rundes Objekt"),
    "weighing_scale": ("Scale", "Waage"),
}

DIRT = {  # DirtLabel name (lowercase): (en, de)
    "unspecified": ("Dirt", "Verschmutzung"),
    "liquid_many": ("Liquid stain", "Flüssiger Fleck"),
    "solid_many": ("Solid dirt", "Feste Verschmutzung"),
    "liquid_massive": ("Large liquid stain", "Großer flüssiger Fleck"),
    "solid_massive": ("Heavy solid dirt", "Starke feste Verschmutzung"),
}

NONE = ("None", "Keine")


def selector(lang: int) -> dict:
    def options(table: dict) -> dict:
        return {"options": {key: names[lang] for key, names in table.items()}}

    return {
        "dirt_type": options(DIRT),
        "furniture_type": options(FURNITURE),
        "obstacle_type": options({**OBSTACLES, "none": NONE}),
    }


def main() -> None:
    for path, lang in [("strings.json", 0), ("translations/en.json", 0), ("translations/de.json", 1)]:
        file = COMPONENT / path
        data = json.loads(file.read_text(encoding="utf-8"))
        data["selector"] = selector(lang)
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("updated", path)


if __name__ == "__main__":
    main()
