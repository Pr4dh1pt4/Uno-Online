"""
Loader & cache asset gambar kartu UNO.

Asset disimpan di client/assets/cards/. Penamaan:
  Red_5.png, Blue_Skip.png, Green_Draw.png, Wild.png, Wild_Draw.png,
  Deck.png (punggung kartu), Banner.png, Table_0.png .. Table_4.png
"""
import os
import pygame

import config

_ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "cards")
_cache: dict[str, pygame.Surface] = {}


def _load(name: str) -> pygame.Surface | None:
    path = os.path.join(_ASSET_DIR, name)
    if not os.path.exists(path):
        return None
    return pygame.image.load(path).convert_alpha()


def card_surface(asset_name: str, w: int = config.CARD_W, h: int = config.CARD_H) -> pygame.Surface:
    """Ambil surface kartu berukuran (w,h), dengan cache."""
    key = f"{asset_name}@{w}x{h}"
    if key in _cache:
        return _cache[key]
    surf = _load(asset_name)
    if surf is None:
        surf = _placeholder(asset_name, w, h)
    else:
        surf = pygame.transform.smoothscale(surf, (w, h))
    _cache[key] = surf
    return surf


def card_back(w: int = config.CARD_W, h: int = config.CARD_H) -> pygame.Surface:
    return card_surface("Deck.png", w, h)


def table_background(index: int = 0) -> pygame.Surface | None:
    surf = _load(f"Table_{index}.png")
    if surf:
        return pygame.transform.smoothscale(surf, (config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    return None


def banner() -> pygame.Surface | None:
    return _load("Banner.png")


def _placeholder(text: str, w: int, h: int) -> pygame.Surface:
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((40, 40, 50))
    pygame.draw.rect(surf, (200, 200, 200), surf.get_rect(), 2, border_radius=8)
    font = pygame.font.SysFont("Arial", 12)
    label = font.render(text.replace(".png", ""), True, (220, 220, 220))
    surf.blit(label, label.get_rect(center=(w // 2, h // 2)))
    return surf
