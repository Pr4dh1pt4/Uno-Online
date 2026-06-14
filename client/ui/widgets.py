import math
import pygame

from client.ui import sounds

class Palette:
    BG = (16, 18, 27)
    BG_GRADIENT_TOP = (20, 22, 35)
    BG_GRADIENT_BOT = (10, 12, 20)
    PANEL = (28, 32, 48)
    PANEL_HOVER = (38, 42, 62)
    PANEL_LIGHT = (48, 54, 76)
    PANEL_BORDER = (60, 66, 92)

    ACCENT = (235, 64, 52)
    ACCENT_HOVER = (255, 90, 78)
    ACCENT_GLOW = (235, 64, 52, 80)

    TEXT = (240, 242, 250)
    TEXT_DIM = (130, 138, 160)
    TEXT_MUTED = (90, 96, 115)

    GREEN = (56, 193, 114)
    GREEN_HOVER = (72, 213, 130)
    YELLOW = (250, 204, 50)
    BLUE = (60, 130, 246)
    BLUE_HOVER = (80, 150, 255)
    GOLD = (218, 180, 56)
    GOLD_GLOW = (218, 180, 56, 60)
    PURPLE = (140, 100, 240)

    UNO_COLORS = {
        "Red": (220, 50, 42),
        "Green": (68, 180, 75),
        "Blue": (46, 120, 210),
        "Yellow": (248, 205, 40),
    }

    RANK_COLORS = {
        "Bronze": (186, 150, 95),
        "Silver": (195, 200, 215),
        "Gold": (218, 180, 56),
        "Platinum": (100, 210, 230),
    }

_font_cache: dict[tuple, pygame.font.Font] = {}

def _get_font(size: int = 22, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _font_cache:
        for name in ("Segoe UI", "Helvetica Neue", "Arial"):
            try:
                _font_cache[key] = pygame.font.SysFont(name, size, bold=bold)
                break
            except Exception:
                continue
        if key not in _font_cache:
            _font_cache[key] = pygame.font.SysFont(None, size, bold=bold)
    return _font_cache[key]

def draw_text(surf, text, pos, size=22, color=None, bold=False, center=False,
              shadow=False, shadow_color=(0, 0, 0)):
    if color is None:
        color = Palette.TEXT
    font = _get_font(size, bold)
    if shadow:
        sh = font.render(str(text), True, shadow_color)
        r = sh.get_rect()
        if center:
            r.center = (pos[0] + 2, pos[1] + 2)
        else:
            r.topleft = (pos[0] + 2, pos[1] + 2)
        surf.blit(sh, r)
    img = font.render(str(text), True, color)
    rect = img.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    surf.blit(img, rect)
    return rect

def draw_gradient_rect(surf, rect, color_top, color_bot, border_radius=0):
    r = pygame.Rect(rect)
    if r.h <= 0 or r.w <= 0:
        return
    temp = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    for y in range(r.h):
        t = y / max(1, r.h - 1)
        c = tuple(int(color_top[i] + (color_bot[i] - color_top[i]) * t) for i in range(3))
        a = 255
        if len(color_top) > 3 and len(color_bot) > 3:
            a = int(color_top[3] + (color_bot[3] - color_top[3]) * t)
        pygame.draw.line(temp, (*c, a), (0, y), (r.w, y))
    if border_radius > 0:
        mask_surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(mask_surf, (255, 255, 255, 255), (0, 0, r.w, r.h),
                         border_radius=border_radius)
        temp.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(temp, r.topleft)

def draw_glow(surf, center, radius, color, intensity=1.0):
    glow_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for i in range(radius, 0, -1):
        alpha = int((i / radius) * 40 * intensity)
        c = (*color[:3], min(255, alpha))
        pygame.draw.circle(glow_surf, c, (radius, radius), i)
    surf.blit(glow_surf, (center[0] - radius, center[1] - radius))

def draw_shadow_rect(surf, rect, offset=4, alpha=50, border_radius=12):
    shadow = pygame.Surface((rect[2] + offset * 2, rect[3] + offset * 2), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, alpha),
                     (offset, offset, rect[2], rect[3]),
                     border_radius=border_radius)
    surf.blit(shadow, (rect[0] - offset, rect[1] - offset))

def draw_bg_gradient(surf, color_top=None, color_bot=None):
    if color_top is None:
        color_top = Palette.BG_GRADIENT_TOP
    if color_bot is None:
        color_bot = Palette.BG_GRADIENT_BOT
    w, h = surf.get_size()
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(color_top[i] + (color_bot[i] - color_top[i]) * t) for i in range(3))
        pygame.draw.line(surf, c, (0, y), (w, y))

def draw_particles(surf, tick, count=30, color=None):
    if color is None:
        color = (255, 255, 255)
    w, h = surf.get_size()
    for i in range(count):
        seed = i * 137 + 42
        x = (seed * 7 + int(tick * 0.02 * ((i % 5) + 1))) % w
        y = (seed * 13 + int(tick * 0.015 * ((i % 3) + 1))) % h
        alpha = 12 + (i * 7) % 20
        radius = 1 + (i % 3)
        ps = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(ps, (*color[:3], alpha), (radius, radius), radius)
        surf.blit(ps, (x, y))

class Button:
    def __init__(self, rect, label, on_click=None, color=None, font_size=20,
                 hover_color=None, icon=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.color = color or Palette.ACCENT
        self.hover_color = hover_color or tuple(min(255, c + 25) for c in self.color)
        self.font_size = font_size
        self.icon = icon
        self.hover = False
        self.enabled = True
        self._press_anim = 0.0

    def handle(self, event):
        if not self.enabled:
            return
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos) and self.on_click:
                self._press_anim = 1.0
                sounds.play("click")
                self.on_click()

    def draw(self, surf):
        if self._press_anim > 0:
            self._press_anim = max(0, self._press_anim - 0.08)

        r = self.rect
        draw_shadow_rect(surf, r, offset=3, alpha=40, border_radius=12)

        if not self.enabled:
            col_top = Palette.PANEL_LIGHT
            col_bot = Palette.PANEL
        elif self.hover:
            col_top = self.hover_color
            col_bot = self.color
        else:
            col_top = self.color
            col_bot = tuple(max(0, c - 20) for c in self.color)

        inset = int(self._press_anim * 2)
        draw_r = r.inflate(-inset * 2, -inset * 2)
        draw_gradient_rect(surf, draw_r, col_top, col_bot, border_radius=12)

        if self.hover and self.enabled:
            pygame.draw.rect(surf, (*self.hover_color[:3],), draw_r, 2, border_radius=12)

        font = _get_font(self.font_size, bold=True)
        txt = font.render(self.label, True, Palette.TEXT)
        txt_col = Palette.TEXT if self.enabled else Palette.TEXT_DIM
        txt = font.render(self.label, True, txt_col)
        surf.blit(txt, txt.get_rect(center=draw_r.center))

class TextInput:
    def __init__(self, rect, placeholder="", password=False, max_len=32):
        self.rect = pygame.Rect(rect)
        self.text = ""
        self.placeholder = placeholder
        self.password = password
        self.max_len = max_len
        self.active = False
        self._cursor_blink = 0.0

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                self.active = False
            elif event.unicode and len(self.text) < self.max_len and event.unicode.isprintable():
                self.text += event.unicode

    def draw(self, surf):
        r = self.rect
        draw_shadow_rect(surf, r, offset=2, alpha=30, border_radius=10)

        pygame.draw.rect(surf, Palette.PANEL, r, border_radius=10)

        if self.active:
            glow_rect = r.inflate(4, 4)
            pygame.draw.rect(surf, (*Palette.ACCENT[:3], 60), glow_rect, 3,
                             border_radius=12)
            pygame.draw.rect(surf, Palette.ACCENT, r, 2, border_radius=10)
        else:
            pygame.draw.rect(surf, Palette.PANEL_BORDER, r, 1, border_radius=10)

        font = _get_font(20)
        shown = ("●" * len(self.text)) if self.password else self.text
        if shown:
            txt = font.render(shown, True, Palette.TEXT)
        else:
            txt = font.render(self.placeholder, True, Palette.TEXT_MUTED)
        clip = pygame.Rect(r.x + 14, r.y, r.w - 28, r.h)
        surf.set_clip(clip)
        surf.blit(txt, (r.x + 14, r.y + (r.h - txt.get_height()) // 2))
        surf.set_clip(None)

        if self.active:
            self._cursor_blink += 0.04
            if math.sin(self._cursor_blink * 3) > 0:
                cx = r.x + 14 + font.size(shown)[0] + 2
                cy1 = r.y + 10
                cy2 = r.y + r.h - 10
                pygame.draw.line(surf, Palette.ACCENT, (cx, cy1), (cx, cy2), 2)
