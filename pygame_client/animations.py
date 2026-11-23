import time
import math
import pygame
from typing import Tuple, Callable, Optional, List

def smoothstep(t: float) -> float:
    """Hermite interpolation for smooth ease-in/ease-out motion."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)

class CardAnimation:
    """
    Smooth, non-blocking 60 FPS Card Animation.
    Interpolates position, rotation, and scale over time.
    """
    def __init__(
        self,
        surface: pygame.Surface,
        start_pos: Tuple[float, float],
        end_pos: Tuple[float, float],
        duration: float = 0.35,
        start_angle: float = 0.0,
        end_angle: float = 0.0,
        start_scale: float = 1.0,
        end_scale: float = 1.0,
        on_complete: Optional[Callable[[], None]] = None
    ):
        self.surface = surface
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.duration = max(0.01, duration)
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.start_scale = start_scale
        self.end_scale = end_scale
        self.on_complete = on_complete

        self.started_at = time.perf_counter()
        self.finished = False

    def update(self) -> Tuple[pygame.Surface, Tuple[float, float]]:
        elapsed = time.perf_counter() - self.started_at
        t = min(1.0, elapsed / self.duration)
        p = smoothstep(t)

        # Interpolate position
        x = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * p
        y = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * p

        # Interpolate angle and scale
        angle = self.start_angle + (self.end_angle - self.start_angle) * p
        scale = self.start_scale + (self.end_scale - self.start_scale) * p

        surf = self.surface
        if abs(scale - 1.0) > 0.01:
            w = max(1, int(surf.get_width() * scale))
            h = max(1, int(surf.get_height() * scale))
            surf = pygame.transform.smoothscale(surf, (w, h))

        if abs(angle) > 0.1:
            surf = pygame.transform.rotate(surf, angle)

        if t >= 1.0 and not self.finished:
            self.finished = True
            if self.on_complete:
                self.on_complete()

        return surf, (x, y)

class FloatingText:
    """Floating points (+5 pts) animation moving from trick to team scoreboard."""
    def __init__(self, text: str, start: Tuple[float, float], end: Tuple[float, float], color=(252, 232, 146), duration=0.8):
        self.text = text
        self.start = start
        self.end = end
        self.color = color
        self.duration = duration
        self.started_at = time.perf_counter()
        self.finished = False

    def update(self) -> Tuple[str, Tuple[float, float], float]:
        elapsed = time.perf_counter() - self.started_at
        t = min(1.0, elapsed / self.duration)
        p = smoothstep(t)
        x = self.start[0] + (self.end[0] - self.start[0]) * p
        y = self.start[1] + (self.end[1] - self.start[1]) * p
        alpha = max(0.0, 1.0 - t * 0.9)
        if t >= 1.0:
            self.finished = True
        return self.text, (x, y), alpha

class AnimationManager:
    """Coordinates all active sprite animations on the table."""
    def __init__(self):
        self.card_animations: List[CardAnimation] = []
        self.floating_texts: List[FloatingText] = []

    def add_card_anim(self, anim: CardAnimation):
        self.card_animations.append(anim)

    def add_floating_text(self, text: str, start: Tuple[float, float], end: Tuple[float, float], color=(252, 232, 146)):
        self.floating_texts.append(FloatingText(text, start, end, color))

    def update_and_draw(self, screen: pygame.Surface, font: pygame.font.Font):
        # 1. Update and draw cards
        active_cards = []
        for anim in self.card_animations:
            surf, pos = anim.update()
            rect = surf.get_rect(center=(int(pos[0]), int(pos[1])))
            screen.blit(surf, rect)
            if not anim.finished:
                active_cards.append(anim)
        self.card_animations = active_cards

        # 2. Update and draw floating texts
        active_texts = []
        for ft in self.floating_texts:
            txt, pos, alpha = ft.update()
            rendered = font.render(txt, True, ft.color)
            rendered.set_alpha(int(alpha * 255))
            screen.blit(rendered, (int(pos[0]), int(pos[1])))
            if not ft.finished:
                active_texts.append(ft)
        self.floating_texts = active_texts

    def is_animating(self) -> bool:
        return len(self.card_animations) > 0
