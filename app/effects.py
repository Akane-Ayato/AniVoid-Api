"""Catalog of cosmetics: ~100 effects + titles + sticker packs. Single source of truth:
   * the shop API serves it (names, rarity, prices),
   * tools/gen_effects.py turns RECIPES into assets/effects.css for the frontend.
Item ids look like "frame.spin_aurora", "name.grad_ember", "banner.aurora_a", "card.gborder_rose", "title.void_walker", "pack.spirits"."""

RANK_NAMES = ["Newcomer", "Void Initiate", "Shadow Watcher", "Rift Walker", "Void Sage", "Ascended"]
RARITY = {  # price (VP), minimum rank index
    "common": (120, 0), "uncommon": (320, 0), "rare": (700, 1), "epic": (1500, 2), "legendary": (3200, 3),
}
PALETTES = {  # name -> three colours (used by rings, gradients, glows)
    "aurora": ("#4ff0d2", "#8a7bff", "#ff5fa8"), "ember": ("#ffd23f", "#ff7a18", "#e63946"),
    "ocean": ("#00e5ff", "#2979ff", "#7c4dff"), "toxic": ("#b6ff3b", "#00e676", "#00bfa5"),
    "royal": ("#fff3b0", "#ffd700", "#b8860b"), "frost": ("#ffffff", "#7fd8ff", "#c9f0ff"),
    "sunset": ("#ffb347", "#ff6a88", "#ff9a8b"), "candy": ("#ff8ad8", "#8ad6ff", "#fff08a"),
    "mint": ("#e8fff5", "#3ddbb0", "#a8ffd9"), "violet": ("#ff9ae6", "#8a3dff", "#d6a8ff"),
    "blood": ("#ff5a73", "#ff0033", "#7a0010"), "mono": ("#ffffff", "#8a8fa3", "#ffffff"),
    "rainbow": ("red", "lime", "blue"),
}
GLOWS = {"aqua": "#4ff0d2", "rose": "#ff5fa8", "gold": "#ffd23f", "lime": "#b6ff3b", "violet": "#a78bff", "white": "#ffffff"}

ITEMS: dict[str, dict] = {}
RECIPES: dict[str, tuple] = {}   # id -> (family, params) consumed by the CSS generator


def _add(kind, key, name, rarity, family, params, *, price=None, min_rank=None):
    iid = f"{kind}.{key}"
    p, r = RARITY[rarity]
    ITEMS[iid] = {"id": iid, "kind": kind, "name": name, "rarity": rarity,
                  "price": p if price is None else price, "min_rank": r if min_rank is None else min_rank}
    RECIPES[iid] = (family, params)


# ------------------------------------------------------------------ frames (avatar effects)
_SPIN_RARITY = {"aurora": "common", "mono": "common", "mint": "common", "frost": "uncommon", "candy": "uncommon", "sunset": "uncommon",
                "ocean": "rare", "toxic": "rare", "violet": "rare", "ember": "epic", "blood": "epic", "royal": "legendary", "rainbow": "legendary"}
for pal in PALETTES:
    _add("frame", f"spin_{pal}", f"{pal.title()} Ring", _SPIN_RARITY[pal], "spin", {"pal": pal})
_FRAME_FAMS = [("pulse", "Pulse", ["aqua", "rose", "gold", "violet"]), ("dash", "Orbit Dash", ["aqua", "rose", "lime", "gold"]),
               ("twin", "Twin Ring", ["ocean", "ember", "violet", "toxic"]), ("blob", "Liquid", ["aurora", "candy", "mint", "sunset"]),
               ("orbit", "Satellite", ["aqua", "gold", "rose", "violet"]), ("ripple", "Ripple", ["ocean", "rose", "toxic", "royal"])]
_RAR4 = ["uncommon", "rare", "rare", "epic"]
for fam, label, cols in _FRAME_FAMS:
    for i, c in enumerate(cols):
        _add("frame", f"{fam}_{c}", f"{c.title()} {label}", _RAR4[i], fam, {"c": c, "pal": c if c in PALETTES else None})
# starter / rank-unlocked frames are free (price 0): they are also what legacy values map to
for iid, rank in {"frame.pulse_aqua": 0, "frame.spin_sunset": 1, "frame.twin_ocean": 2, "frame.spin_ember": 3, "frame.spin_violet": 4, "frame.spin_rainbow": 5}.items():
    ITEMS[iid]["price"], ITEMS[iid]["min_rank"] = 0, rank
LEGACY_FRAMES = {"glow": "frame.pulse_aqua", "sakura": "frame.spin_sunset", "neon": "frame.twin_ocean",
                 "flame": "frame.spin_ember", "galaxy": "frame.spin_violet", "rainbow": "frame.spin_rainbow"}

# ------------------------------------------------------------------ name effects
for i, pal in enumerate(["aurora", "ember", "ocean", "toxic", "royal", "frost", "sunset", "candy", "mint", "violet"]):
    _add("name", f"grad_{pal}", f"{pal.title()} Gradient", ["common", "common", "uncommon", "uncommon", "rare", "uncommon", "uncommon", "rare", "common", "rare"][i], "grad", {"pal": pal})
for i, g in enumerate(GLOWS):
    _add("name", f"glow_{g}", f"{g.title()} Glow", ["common", "uncommon", "uncommon", "uncommon", "rare", "common"][i], "glow", {"col": GLOWS[g]})
for i, g in enumerate(["aqua", "rose", "gold", "violet"]):
    _add("name", f"shimmer_{g}", f"{g.title()} Shimmer", ["rare", "rare", "epic", "epic"][i], "shimmer", {"col": GLOWS[g]})
for i, g in enumerate(["aqua", "rose", "lime"]):
    _add("name", f"flicker_{g}", f"{g.title()} Neon", ["rare", "rare", "epic"][i], "flicker", {"col": GLOWS[g]})
for i, g in enumerate(["aqua", "rose"]):
    _add("name", f"glitch_{g}", f"{g.title()} Glitch", "epic", "glitch", {"col": GLOWS[g]})
_add("name", "rainbow", "Rainbow Flow", "legendary", "rainbowtext", {})
_add("name", "metal_gold", "Liquid Gold", "legendary", "metal", {})
_add("name", "outline", "Hollow Neon", "rare", "outline", {"col": GLOWS["aqua"]})

# ------------------------------------------------------------------ banner overlays
for i, pal in enumerate(["aurora", "ocean", "sunset", "violet"]):
    _add("banner", f"aurora_{pal}", f"{pal.title()} Aurora", ["uncommon", "uncommon", "rare", "rare"][i], "b_aurora", {"pal": pal})
for i, g in enumerate(["white", "aqua", "gold"]):
    _add("banner", f"stars_{g}", f"{g.title()} Starfield", ["common", "uncommon", "rare"][i], "b_stars", {"col": GLOWS[g]})
for i, g in enumerate(["aqua", "rose"]):
    _add("banner", f"rain_{g}", f"{g.title()} Rain", "rare", "b_rain", {"col": GLOWS[g]})
for i, g in enumerate(["aqua", "rose"]):
    _add("banner", f"scan_{g}", f"{g.title()} Scanlines", "uncommon", "b_scan", {"col": GLOWS[g]})
for i, g in enumerate(["violet", "aqua"]):
    _add("banner", f"grid_{g}", f"{g.title()} Grid", "rare", "b_grid", {"col": GLOWS[g]})
for i, pal in enumerate(["candy", "aurora", "ember"]):
    _add("banner", f"bokeh_{pal}", f"{pal.title()} Bokeh", ["uncommon", "rare", "rare"][i], "b_bokeh", {"pal": pal})
for i, pal in enumerate(["ocean", "sunset"]):
    _add("banner", f"waves_{pal}", f"{pal.title()} Waves", "epic", "b_waves", {"pal": pal})
for i, g in enumerate(["gold", "rose"]):
    _add("banner", f"sparks_{g}", f"{g.title()} Embers", "epic", "b_sparks", {"col": GLOWS[g]})

# ------------------------------------------------------------------ comment / profile card styles
for i, pal in enumerate(["aurora", "ember", "ocean", "violet", "mint", "sunset"]):
    _add("card", f"gborder_{pal}", f"{pal.title()} Edge", ["uncommon", "uncommon", "rare", "rare", "uncommon", "rare"][i], "c_gborder", {"pal": pal})
for i, g in enumerate(["aqua", "rose", "violet"]):
    _add("card", f"glass_{g}", f"{g.title()} Glass", ["common", "common", "uncommon"][i], "c_glass", {"col": GLOWS[g]})
for i, pal in enumerate(["aurora", "candy"]):
    _add("card", f"holo_{pal}", f"{pal.title()} Hologram", "epic", "c_holo", {"pal": pal})
for i, g in enumerate(["aqua", "rose", "gold"]):
    _add("card", f"neon_{g}", f"{g.title()} Neon Box", ["rare", "rare", "epic"][i], "c_neon", {"col": GLOWS[g]})
for i, pal in enumerate(["ocean", "ember"]):
    _add("card", f"flow_{pal}", f"{pal.title()} Flow", "epic", "c_flow", {"pal": pal})

EFFECT_COUNT = len(ITEMS)

# ------------------------------------------------------------------ titles (text badges next to the name)
_TITLES = [  # key, label, rarity
    ("wanderer", "Wanderer", "common"), ("night_owl", "Night Owl", "common"), ("binge_pilot", "Binge Pilot", "common"), ("opening_skipper", "Opening Skipper", "common"),
    ("side_character", "Side Character", "common"), ("sub_enjoyer", "Sub Enjoyer", "common"), ("dub_defender", "Dub Defender", "common"), ("filler_survivor", "Filler Survivor", "common"),
    ("plot_twist", "Plot Twist", "uncommon"), ("cliffhanger", "Cliffhanger", "uncommon"), ("slice_of_life", "Slice of Life", "uncommon"), ("shonen_spirit", "Shonen Spirit", "uncommon"),
    ("mecha_pilot", "Mecha Pilot", "uncommon"), ("credits_watcher", "Credits Watcher", "uncommon"), ("ost_addict", "OST Addict", "uncommon"), ("hype_train", "Hype Train", "uncommon"),
    ("main_character", "Main Character", "rare"), ("isekai_veteran", "Isekai Veteran", "rare"), ("tsundere_whisperer", "Tsundere Whisperer", "rare"), ("season_finale", "Season Finale", "rare"),
    ("rewatch_royalty", "Rewatch Royalty", "rare"), ("plot_armor", "Plot Armor", "rare"), ("frame_collector", "Frame Collector", "rare"), ("rift_runner", "Rift Runner", "rare"),
    ("void_walker", "Void Walker", "epic"), ("sakuga_sage", "Sakuga Sage", "epic"), ("final_boss", "Final Boss", "epic"), ("neon_samurai", "Neon Samurai", "epic"),
    ("dimension_hopper", "Dimension Hopper", "epic"), ("starlit_sage", "Starlit Sage", "epic"),
    ("anime_oracle", "Anime Oracle", "legendary"), ("eternal_watcher", "Eternal Watcher", "legendary"), ("legend_of_the_void", "Legend of the Void", "legendary"), ("void_emperor", "Void Emperor", "legendary"),
]
for key, label, rar in _TITLES:
    _add("title", key, label, rar, "title", {})

# ------------------------------------------------------------------ sticker packs + reactions + glyphs
STICKERS = {
    "blobs": ["happy", "sad", "angry", "love", "shock", "sleepy", "cool", "laugh"],
    "words": ["gg", "omg", "wow", "lol", "nice", "hype", "rip", "uwu"],
    "spirits": ["boo", "shy", "smug", "dizzy", "sick", "panic", "zen", "glee"],
    "sparks": ["heart", "star", "flame", "drop", "bolt", "ring", "crown", "sparkle"],
    "critters": ["cat_happy", "cat_sleepy", "cat_angry", "cat_love", "fox_wink", "fox_smug", "bun_shy", "bun_happy"],
}
PACK_META = {"blobs": ("Blobbies", 0), "words": ("Hype Words", 0), "spirits": ("Little Spirits", 600), "sparks": ("Living Sparks", 800), "critters": ("Critter Club", 1000)}
for pk, (label, price) in PACK_META.items():
    ITEMS[f"pack.{pk}"] = {"id": f"pack.{pk}", "kind": "pack", "name": label, "rarity": "common" if price == 0 else ("rare" if price < 900 else "epic"), "price": price, "min_rank": 0}

REACTIONS = ["like", "love", "haha", "wow", "sad", "angry", "fire", "clap"]
AVATAR_GLYPHS = ["initial", "fox", "cat", "wolf", "dragon", "ghost", "flower", "bolt", "flame", "moon", "star", "headphones", "sword", "crown", "heart", "skull", "bunny", "owl"]
BANNER_PRESETS = [f"p{i}" for i in range(1, 9)]
TITLE_COLORS = 20

KIND_SLOTS = ["frame", "name", "banner", "card", "title"]   # equip slots


def sticker_ok(code: str) -> bool:
    pack, _, sid = (code or "").partition(":")
    return sid in STICKERS.get(pack, [])
