from shared.constants import COLORS, WILD_COLOR

class Card:

    __slots__ = ("color", "ctype")

    def __init__(self, color: str, ctype: str):
        self.color = color
        self.ctype = ctype

    @property
    def is_number(self) -> bool:
        return self.ctype.isdigit()

    @property
    def is_action(self) -> bool:
        return self.ctype in ("Skip", "Reverse", "Draw")

    @property
    def is_wild(self) -> bool:
        return self.color == WILD_COLOR

    @property
    def is_draw_two(self) -> bool:
        return self.ctype == "Draw"

    @property
    def is_wild_draw_four(self) -> bool:
        return self.ctype == "Wild_Draw"

    @property
    def is_any_draw(self) -> bool:
        return self.is_draw_two or self.is_wild_draw_four

    @property
    def asset_name(self) -> str:
        if self.is_wild:
            return f"{self.ctype}.png"
        return f"{self.color}_{self.ctype}.png"

    def matches(self, top: "Card", active_color: str) -> bool:
        if self.is_wild:
            return True
        if self.color == active_color:
            return True
        if self.ctype == top.ctype:
            return True
        return False

    def to_dict(self) -> dict:
        return {"color": self.color, "ctype": self.ctype}

    @staticmethod
    def from_dict(d: dict) -> "Card":
        return Card(d["color"], d["ctype"])

    def __eq__(self, other):
        return isinstance(other, Card) and self.color == other.color and self.ctype == other.ctype

    def __repr__(self):
        return f"Card({self.color}_{self.ctype})"
