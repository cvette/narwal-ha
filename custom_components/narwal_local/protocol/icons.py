"""Material Design Icons for map objects.

Icon names refer to @mdi/font 7.4.47; scripts/build_icon_font.py cuts the
webfont down to exactly these icons (assets/mdi-subset.ttf, Apache 2.0, see
assets/NOTICE.md). Home Assistant uses the same icon set, so the map matches
the rest of the UI.
"""

from __future__ import annotations

from functools import cache
import json
from pathlib import Path
from typing import Any

from .enums import DirtLabel, FurnitureType, ObstacleLabel

ASSETS = Path(__file__).parent / "assets"
FONT_PATH = ASSETS / "mdi-subset.ttf"

OBSTACLE_ICONS: dict[ObstacleLabel, str] = {
    ObstacleLabel.UNSPECIFIED: "shape-outline",
    ObstacleLabel.CABLE: "power-plug",
    ObstacleLabel.TISSUE: "paper-roll",
    ObstacleLabel.POOP: "emoticon-poop",
    ObstacleLabel.LIQUID: "water",
    ObstacleLabel.SHOES: "shoe-sneaker",
    ObstacleLabel.SOLID: "cube-outline",
    ObstacleLabel.SOCKS: "foot-print",  # MDI has no sock
    ObstacleLabel.PLASTIC_BAG: "shopping-outline",
    ObstacleLabel.TRASH_BIN: "trash-can-outline",
    ObstacleLabel.NORMAL: "cancel",
    ObstacleLabel.UNCLEANABLE: "alert-octagon",
    ObstacleLabel.TEXTILES: "tshirt-crew",
    ObstacleLabel.NOT_EXIST: "circle-outline",
    ObstacleLabel.GROUND_TEXTURE: "texture",
    ObstacleLabel.PET: "paw",
    ObstacleLabel.CLIFF: "stairs-down",
    ObstacleLabel.SQUATTING_WC: "toilet",
    ObstacleLabel.CHAIR_U_LEGS: "chair-school",
    ObstacleLabel.CHAIR_WHEEL: "chair-rolling",
    ObstacleLabel.FLOOR_MIRROR: "mirror",
    ObstacleLabel.BOOK: "book-open-variant",
    ObstacleLabel.STICK: "magic-staff",
    ObstacleLabel.MERGE_FLEXIBLE: "sack",
    ObstacleLabel.JEWELRY: "ring",
    ObstacleLabel.PHONE: "cellphone",
    ObstacleLabel.WALLET: "wallet",
    ObstacleLabel.KEY: "key",
    ObstacleLabel.BANKNOTE: "cash",
    ObstacleLabel.REMOTE_CONTROL: "remote",
    ObstacleLabel.GLASSES: "glasses",
    ObstacleLabel.WATCH: "watch",
    ObstacleLabel.CARD: "credit-card",
    ObstacleLabel.HEADPHONES: "headphones",
    ObstacleLabel.BABY_TOY: "teddy-bear",
    ObstacleLabel.PLANT: "sprout",
    ObstacleLabel.FITNESS_EQUIPMENT: "dumbbell",
    ObstacleLabel.PET_TOY: "bone",
    ObstacleLabel.DANGEROUS_GOODS: "fire",
    ObstacleLabel.DECORATION: "flower",
    ObstacleLabel.PAPER_BOX: "package-variant",
    ObstacleLabel.PET_CAT: "cat",
    ObstacleLabel.PET_DOG: "dog",
}

FURNITURE_ICONS: dict[FurnitureType, str] = {
    FurnitureType.UNSPECIFIED: "cube-outline",
    FurnitureType.SINGLE_BED: "bed-single",
    FurnitureType.DOUBLE_BED: "bed-double",
    FurnitureType.BABY_BED: "cradle",
    FurnitureType.DINNER_TABLE_SQUARE: "table-chair",
    FurnitureType.DINNER_TABLE_ROUND: "table-chair",
    FurnitureType.TEA_TABLE_SQUARE: "table-furniture",
    FurnitureType.TEA_TABLE_ROUND: "table-furniture",
    FurnitureType.TV_CUPBOARD: "television-classic",
    FurnitureType.BEDSIDE_TABLE: "dresser-outline",
    FurnitureType.LOCKER: "cupboard",
    FurnitureType.WARDROBE: "wardrobe",
    FurnitureType.SHOE_CUPBOARD: "shoe-formal",
    FurnitureType.SOFA_SINGLE: "sofa-single",
    FurnitureType.SOFA_MULTI: "sofa",
    FurnitureType.SOFA_L_SHAPE: "sofa",
    FurnitureType.SOFA_LAZY: "seat",
    FurnitureType.CHAIR: "chair-school",
    FurnitureType.BAR_CHAIR: "stool",
    FurnitureType.CAT_TOILET: "cat",
    FurnitureType.PET_EATING_AREA: "bowl-outline",
    FurnitureType.PET_HOUSE: "paw-outline",
    FurnitureType.WASHING_MACHINE: "washing-machine",
    FurnitureType.REFRIGERATOR: "fridge",
    FurnitureType.VERTICAL_AIRCON: "air-conditioner",
    FurnitureType.VERTICAL_FAN: "fan",
    FurnitureType.POTTED_PLANT: "flower-tulip",
    FurnitureType.FLOOR_MIRROR: "mirror",
    FurnitureType.TOILET: "toilet",
    FurnitureType.PIANO: "piano",
    FurnitureType.SOFA_U_SHAPE: "sofa",
    FurnitureType.DESK: "desk",
    FurnitureType.GRAND_PIANO: "piano",
    FurnitureType.WASHBASIN: "faucet",
    FurnitureType.COOKER_HOOD_STOVE: "stove",
    FurnitureType.WINE_CABINET: "glass-wine",
    FurnitureType.CAT_HOUSE: "home-roof",
    FurnitureType.DOG_HOUSE: "dog-side",
    FurnitureType.ROUND_PLACEHOLDER: "circle-outline",
    FurnitureType.WEIGHING_SCALE: "scale-bathroom",
}

DIRT_ICONS: dict[DirtLabel, str] = {
    DirtLabel.UNSPECIFIED: "broom",
    DirtLabel.LIQUID_MANY: "liquid-spot",
    DirtLabel.SOLID_MANY: "grain",
    DirtLabel.LIQUID_MASSIVE: "liquid-spot",
    DirtLabel.SOLID_MASSIVE: "grain",
}

DOCK_ICON = "lightning-bolt"


def all_icon_names() -> set[str]:
    return {
        *OBSTACLE_ICONS.values(),
        *FURNITURE_ICONS.values(),
        *DIRT_ICONS.values(),
        DOCK_ICON,
    }


@cache
def codepoints() -> dict[str, int]:
    """Icon name -> codepoint in the bundled subset (empty if not built)."""
    try:
        return json.loads((ASSETS / "icons.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def glyph(name: str) -> str | None:
    """The character to draw for an icon, or None if the subset lacks it."""
    cp = codepoints().get(name)
    return chr(cp) if cp is not None else None


def obstacle_icon(label: Any) -> str:
    return OBSTACLE_ICONS.get(label, OBSTACLE_ICONS[ObstacleLabel.UNSPECIFIED])


def furniture_icon(ftype: Any) -> str:
    return FURNITURE_ICONS.get(ftype, FURNITURE_ICONS[FurnitureType.UNSPECIFIED])


def dirt_icon(label: Any) -> str:
    return DIRT_ICONS.get(label, DIRT_ICONS[DirtLabel.UNSPECIFIED])
