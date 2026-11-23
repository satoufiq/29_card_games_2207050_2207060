import os
import pygame
from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 120
CARD_HEIGHT = 175
CARD_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "cards")

SUIT_SYMBOLS = {
    "Spades": "♠",
    "Hearts": "♥",
    "Clubs": "♣",
    "Diamonds": "♦"
}

SUIT_COLORS = {
    "Spades": (26, 26, 28),
    "Hearts": (201, 35, 35),
    "Clubs": (26, 26, 28),
    "Diamonds": (201, 35, 35)
}

CARD_POINTS = {
    "J": 3,
    "9": 2,
    "A": 1,
    "10": 1,
    "K": 0,
    "Q": 0,
    "8": 0,
    "7": 0
}

def ensure_assets_dir():
    os.makedirs(CARD_DIR, exist_ok=True)

def generate_card_surface(rank: str, suit: str) -> pygame.Surface:
    """Generates an ivory playing card surface with corner pips, point badge, and center art."""
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Ivory background with rounded corners and subtle drop border
    draw.rounded_rectangle(
        [(1, 1), (CARD_WIDTH - 2, CARD_HEIGHT - 2)],
        radius=10,
        fill=(250, 247, 238, 255),
        outline=(180, 170, 150, 255),
        width=2
    )

    color = SUIT_COLORS.get(suit, (26, 26, 28))
    sym = SUIT_SYMBOLS.get(suit, "")
    pts = CARD_POINTS.get(rank, 0)

    # Load default font
    try:
        font_corner = ImageFont.truetype("arial.ttf", 16)
        font_center = ImageFont.truetype("arial.ttf", 36)
        font_pts = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        font_corner = ImageFont.load_default()
        font_center = font_corner
        font_pts = font_corner

    # Top-left corner
    draw.text((8, 6), f"{rank}\n{sym}", fill=color, font=font_corner, spacing=0)

    # Point badge top-right
    badge_text = f"{pts}p"
    draw.rounded_rectangle([(CARD_WIDTH - 26, 6), (CARD_WIDTH - 6, 18)], radius=3, fill=(24, 34, 28, 255))
    draw.text((CARD_WIDTH - 23, 7), badge_text, fill=(252, 232, 146, 255), font=font_pts)

    # Center court crest or big suit symbol
    if rank in ("J", "Q", "K"):
        # Court card crest
        draw.rounded_rectangle(
            [(24, 34), (CARD_WIDTH - 24, CARD_HEIGHT - 34)],
            radius=6,
            fill=(242, 236, 222, 255),
            outline=(212, 175, 55, 180),
            width=1
        )
        draw.text((CARD_WIDTH // 2 - 14, CARD_HEIGHT // 2 - 24), rank, fill=color, font=font_center)
        draw.text((CARD_WIDTH // 2 - 10, CARD_HEIGHT // 2 + 12), sym, fill=color, font=font_corner)
    else:
        # Pips
        draw.text((CARD_WIDTH // 2 - 12, CARD_HEIGHT // 2 - 20), sym, fill=color, font=font_center)

    # Bottom-right corner (inverted)
    draw.text((CARD_WIDTH - 20, CARD_HEIGHT - 36), f"{rank}\n{sym}", fill=color, font=font_corner, spacing=0)

    mode = img.mode
    size = img.size
    data = img.tobytes()
    return pygame.image.fromstring(data, size, mode).convert_alpha()

def generate_card_back() -> pygame.Surface:
    """Generates an authentic luxury card back with royal filigree pattern."""
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded outer border
    draw.rounded_rectangle(
        [(1, 1), (CARD_WIDTH - 2, CARD_HEIGHT - 2)],
        radius=10,
        fill=(68, 14, 22, 255), # Deep Burgundy
        outline=(212, 175, 55, 255), # Gold trim
        width=3
    )

    # Inner gold border
    draw.rounded_rectangle(
        [(6, 6), (CARD_WIDTH - 7, CARD_HEIGHT - 7)],
        radius=6,
        fill=(42, 8, 14, 255),
        outline=(180, 145, 45, 200),
        width=1
    )

    # Center medallion
    cx, cy = CARD_WIDTH // 2, CARD_HEIGHT // 2
    draw.ellipse([(cx - 24, cy - 32), (cx + 24, cy + 32)], fill=(68, 14, 22, 255), outline=(212, 175, 55, 255), width=2)
    
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.text((cx - 12, cy - 10), "29", fill=(252, 232, 146, 255), font=font)

    mode = img.mode
    size = img.size
    data = img.tobytes()
    return pygame.image.fromstring(data, size, mode).convert_alpha()

class CardAssetManager:
    """Caches all 32 card surfaces and the card back for 60 FPS performance."""
    def __init__(self):
        self.cards = {}
        self.card_back = None
        self._load_all()

    def _load_all(self):
        ranks = ["7", "8", "9", "10", "J", "Q", "K", "A"]
        suits = ["Spades", "Hearts", "Clubs", "Diamonds"]

        for suit in suits:
            for rank in ranks:
                code = f"{rank}{suit[0]}"
                self.cards[code] = generate_card_surface(rank, suit)

        self.card_back = generate_card_back()

    def get_card(self, code: str) -> pygame.Surface:
        return self.cards.get(code, self.card_back)

    def get_back(self) -> pygame.Surface:
        return self.card_back
