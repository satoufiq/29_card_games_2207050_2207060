import sys
import os
import pygame
from typing import Optional, List, Dict, Tuple

from card import Card
from game_state import Phase
from rules import Rules
from game_controller import GameController
from pygame_client.assets_gen import CardAssetManager, CARD_WIDTH, CARD_HEIGHT
from pygame_client.animations import AnimationManager, CardAnimation

# 1280x720 standard desktop window resolution
WIN_WIDTH = 1280
WIN_HEIGHT = 720

# Color Palette
FELT_CENTER = (13, 56, 34)
FELT_MID = (9, 39, 24)
FELT_EDGE = (5, 22, 14)
WOOD_RIM = (61, 27, 6)
WOOD_BORDER = (35, 13, 2)
GOLD_TRIM = (212, 175, 55)
GOLD_BRIGHT = (252, 232, 146)
CHARCOAL_PANEL = (18, 25, 34)
CHARCOAL_BORDER = (212, 175, 55)
TEAM_A_GOLD = (229, 184, 66)
TEAM_B_BLUE = (58, 134, 255)
TEXT_WHITE = (255, 255, 255)
TEXT_MUTED = (160, 185, 170)

class Button:
    def __init__(self, rect: pygame.Rect, text: str, bg_color=(28, 40, 32), text_color=TEXT_WHITE, border_color=GOLD_TRIM):
        self.rect = rect
        self.text = text
        self.bg_color = bg_color
        self.text_color = text_color
        self.border_color = border_color
        self.is_hovered = False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font):
        color = (min(255, self.bg_color[0] + 25), min(255, self.bg_color[1] + 25), min(255, self.bg_color[2] + 25)) if self.is_hovered else self.bg_color
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        pygame.draw.rect(screen, self.border_color, self.rect, width=1, border_radius=6)

        txt_surf = font.render(self.text, True, self.text_color)
        txt_rect = txt_surf.get_rect(center=self.rect.center)
        screen.blit(txt_surf, txt_rect)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

class PygameApp:
    def __init__(self, human_mode: bool = True):
        pygame.init()
        pygame.display.set_caption("Intelligent 29 Cards Game")
        self.screen = pygame.display.set_mode((WIN_WIDTH, WIN_HEIGHT))
        self.clock = pygame.time.Clock()

        # Fonts
        self.font_title = pygame.font.SysFont("arial", 20, bold=True)
        self.font_main = pygame.font.SysFont("arial", 14, bold=True)
        self.font_small = pygame.font.SysFont("arial", 12)
        self.font_large = pygame.font.SysFont("arial", 32, bold=True)
        self.font_emblem = pygame.font.SysFont("arial", 54, bold=True)

        # Asset & Animation Manager
        self.asset_mgr = CardAssetManager()
        self.anim_mgr = AnimationManager()

        # Game Engine Controller. The desktop client has no doubling or Single Hand
        # prompts, so those optional house rules are switched off here (the web table supports them).
        from house_rules import HouseRules, SingleHandRules
        self.controller = GameController(
            human_seat=0 if human_mode else None,
            rules=HouseRules(double_redouble=False, single_hand=SingleHandRules(enabled=False)))
        self.current_mode = "human" if human_mode else "ai"

        # Interactive states
        self.hovered_card_idx = -1
        self.is_ai_paused = False
        self.ai_speed = 1.0
        self.last_step_time = 0.0
        self.show_rules = False
        self.show_inspector = False

        # Seat positions
        self.seat_coords = {
            2: (WIN_WIDTH // 2, 90),          # North
            1: (180, WIN_HEIGHT // 2),        # West
            3: (WIN_WIDTH - 180, WIN_HEIGHT // 2), # East
            0: (WIN_WIDTH // 2, WIN_HEIGHT - 100) # South (Human)
        }

        # Central trick slot positions
        self.trick_coords = {
            2: (WIN_WIDTH // 2, WIN_HEIGHT // 2 - 75),  # North card
            1: (WIN_WIDTH // 2 - 105, WIN_HEIGHT // 2), # West card
            3: (WIN_WIDTH // 2 + 105, WIN_HEIGHT // 2), # East card
            0: (WIN_WIDTH // 2, WIN_HEIGHT // 2 + 75)   # South card
        }

        # Control Buttons
        self.btn_mode = Button(pygame.Rect(WIN_WIDTH - 380, 10, 110, 30), "4-AI Mode" if human_mode else "Human Mode")
        self.btn_rules = Button(pygame.Rect(WIN_WIDTH - 260, 10, 75, 30), "Rules")
        self.btn_inspector = Button(pygame.Rect(WIN_WIDTH - 175, 10, 85, 30), "Inspector")
        self.btn_pause = Button(pygame.Rect(WIN_WIDTH - 80, 10, 70, 30), "Pause")

        # Bidding Buttons
        self.bidding_buttons: List[Button] = []
        # Trump Selection Buttons
        self.trump_buttons: List[Tuple[pygame.Rect, str]] = []
        self.trump_card_rects: List[Tuple[pygame.Rect, Any]] = []

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0

            # 1. Process Events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.show_rules = False
                        self.show_inspector = False
                    elif event.key == pygame.K_SPACE:
                        self.is_ai_paused = not self.is_ai_paused
                self._handle_event(event)

            # 2. Game Step
            self._update_game(dt)

            # 3. Draw Scene
            self._draw_scene()

            pygame.display.flip()

        pygame.quit()

    def _handle_event(self, event: pygame.event.Event):
        # Header button actions
        if self.btn_mode.handle_event(event):
            if self.current_mode == "human":
                self.current_mode = "ai"
                self.controller.human_seat = None
                self.btn_mode.text = "Human Mode"
            else:
                self.current_mode = "human"
                self.controller.human_seat = 0
                self.btn_mode.text = "4-AI Mode"

        if self.btn_rules.handle_event(event):
            self.show_rules = not self.show_rules
            self.show_inspector = False

        if self.btn_inspector.handle_event(event):
            self.show_inspector = not self.show_inspector
            self.show_rules = False

        if self.btn_pause.handle_event(event):
            self.is_ai_paused = not self.is_ai_paused
            self.btn_pause.text = "Play" if self.is_ai_paused else "Pause"

        # Bidding panel actions
        state = self.controller.state

        # Deal Abandoned Dismissal Click
        if state.deal_abandoned:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.controller.start_next_deal_after_abandonment()
                return

        if state.phase == Phase.BIDDING and self.controller.is_human_turn() and self.current_mode == "human":
            for btn in self.bidding_buttons:
                if btn.handle_event(event):
                    if btn.text == "PASS":
                        self.controller.human_bid(None)
                    else:
                        val = int(btn.text.split()[0])
                        self.controller.human_bid(val)
                    break

        # Human Card Clicks (South Hand)
        if state.phase == Phase.PLAYING and self.controller.is_human_turn() and self.current_mode == "human":
            if event.type == pygame.MOUSEMOTION:
                self._check_hand_hover(event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._check_hand_click(event.pos)

        # Trump Selection Clicks
        if state.phase == Phase.TRUMP_SELECTION and self.controller.is_human_turn() and self.current_mode == "human":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._check_trump_select_click(event.pos)

        # Completed Trick Advance Click
        if state.pending_trick_pause:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.controller.clear_completed_trick()

        # Round Over Next Hand Click
        if state.phase == Phase.ROUND_OVER:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.controller.next_round()

    def _check_hand_hover(self, mouse_pos: Tuple[int, int]):
        state = self.controller.state
        hand = state.hands[0]
        n = len(hand)
        if n == 0:
            self.hovered_card_idx = -1
            return

        spacing = 65
        total_w = (n - 1) * spacing + CARD_WIDTH
        start_x = (WIN_WIDTH - total_w) // 2
        y = WIN_HEIGHT - CARD_HEIGHT - 15

        self.hovered_card_idx = -1
        # Test from right to left so overlapping cards detect properly
        for i in reversed(range(n)):
            x = start_x + i * spacing
            rect = pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT)
            if rect.collidepoint(mouse_pos):
                self.hovered_card_idx = i
                break

    def _check_hand_click(self, mouse_pos: Tuple[int, int]):
        if self.hovered_card_idx >= 0:
            hand = self.controller.state.hands[0]
            if self.hovered_card_idx < len(hand):
                card = hand[self.hovered_card_idx]
                legal_cards = Rules.get_legal_cards(0, self.controller.state)
                if card in legal_cards:
                    self.controller.human_play_card(card)

    def _check_trump_select_click(self, mouse_pos: Tuple[int, int]):
        # 1. Check trump option buttons (4 suits + 7th card)
        for rect, opt in self.trump_buttons:
            if rect.collidepoint(mouse_pos):
                self.controller.human_select_trump_option(opt)
                return

        # 2. Check cards in hand
        for rect, card in self.trump_card_rects:
            if rect.collidepoint(mouse_pos):
                self.controller.human_select_trump(card)
                return

    def _update_game(self, dt: float):
        state = self.controller.state

        # Auto-step AI turns if human mode and waiting for AI
        if self.current_mode == "human":
            if not self.controller.is_human_turn() and not state.pending_trick_pause:
                self.controller.step()
        else:
            # 4-AI simulation mode
            if not self.is_ai_paused:
                if state.pending_trick_pause:
                    # Brief delay before clearing trick
                    pygame.time.delay(500)
                    self.controller.clear_completed_trick()
                elif state.phase == Phase.ROUND_OVER:
                    pygame.time.delay(1000)
                    self.controller.next_round()
                else:
                    self.controller.step()

    def _draw_scene(self):
        self.screen.fill((4, 8, 6))

        # 1. Emerald Green Felt Oval Table
        table_rect = pygame.Rect(60, 55, WIN_WIDTH - 120, WIN_HEIGHT - 110)
        # Mahogany wood rim
        pygame.draw.ellipse(self.screen, WOOD_RIM, table_rect)
        pygame.draw.ellipse(self.screen, GOLD_TRIM, table_rect, width=2)
        # Felt inner
        inner_rect = table_rect.inflate(-20, -20)
        pygame.draw.ellipse(self.screen, FELT_CENTER, inner_rect)
        pygame.draw.ellipse(self.screen, (212, 175, 55, 60), inner_rect, width=1)

        # 2. Top HUD Bar
        self._draw_top_hud()

        # 3. Player Seats & Hand Stacks
        self._draw_player_seats()

        # 4. Scoreboard Cards (Section 3)
        self._draw_scoreboards()

        # 5. Center Trick Area
        self._draw_trick_area()

        # 5b. Table Trump Card Entity (Concealed or Revealed)
        self._draw_table_trump_card()

        # 6. Human South Hand (Overlapping Fan)
        self._draw_human_hand()

        # 7. Modals (Bidding, Trump Select, Round Result, Rules, Inspector)
        self._draw_modals()

        # 8. Active animations
        self.anim_mgr.update_and_draw(self.screen, self.font_main)

    def _draw_top_hud(self):
        state = self.controller.state

        # Bar background
        pygame.draw.rect(self.screen, (10, 16, 12), pygame.Rect(0, 0, WIN_WIDTH, 48))
        pygame.draw.line(self.screen, GOLD_TRIM, (0, 48), (WIN_WIDTH, 48), 1)

        # Title & Match tracker
        txt_title = self.font_title.render("INTELLIGENT 29", True, GOLD_BRIGHT)
        self.screen.blit(txt_title, (24, 6))
        txt_trick = self.font_small.render(f"HAND {state.round_number:02d} · TRICK {len(state.completed_tricks)+1:02d}/08", True, TEXT_MUTED)
        self.screen.blit(txt_trick, (24, 28))

        # Contract Badge
        target = state.target_bid if state.target_bid > 0 else state.bid
        bidder_txt = f"P{state.highest_bidder}" if state.highest_bidder is not None else "--"
        c_color = TEAM_A_GOLD if (state.highest_bidder in (0, 2)) else TEAM_B_BLUE if state.highest_bidder is not None else GOLD_BRIGHT
        txt_contract = self.font_main.render(f"CONTRACT: {target if target > 0 else '--'} ({bidder_txt})", True, c_color)
        self.screen.blit(txt_contract, (320, 14))

        # Trump Status Badge
        if state.trump_revealed and state.trump_suit:
            t_txt = f"TRUMP: {state.trump_suit.symbol} {state.trump_suit.value.upper()}"
            txt_trump = self.font_main.render(t_txt, True, GOLD_BRIGHT)
        elif state.highest_bidder == 0 and self.current_mode == "human" and state.trump_suit:
            card_info = f"({state.seventh_card.code} · 7th)" if (state.is_seventh_card_trump and state.seventh_card) else ("(7th Card)" if state.is_seventh_card_trump else "(Secret)")
            t_txt = f"TRUMP: {state.trump_suit.symbol} {state.trump_suit.value.upper()} {card_info}"
            txt_trump = self.font_main.render(t_txt, True, (147, 197, 253))
        else:
            txt_trump = self.font_main.render("TRUMP: [LOCKED] HIDDEN", True, (160, 175, 170))
        self.screen.blit(txt_trump, (530, 14))

        # Buttons
        self.btn_mode.draw(self.screen, self.font_small)
        self.btn_rules.draw(self.screen, self.font_small)
        self.btn_inspector.draw(self.screen, self.font_small)
        self.btn_pause.draw(self.screen, self.font_small)

    def _draw_player_seats(self):
        state = self.controller.state

        # Position South avatar cleanly to the left of the hand when in human mode, or centered in AI mode
        self.seat_coords[0] = (WIN_WIDTH // 2 - 330, WIN_HEIGHT - 75) if self.current_mode == "human" else (WIN_WIDTH // 2, WIN_HEIGHT - 95)

        south_name = "South (You)" if self.current_mode == "human" else "South (AI 0)"
        seats = [
            (0, south_name, TEAM_A_GOLD),
            (2, "North (Partner)" if self.current_mode == "human" else "North (AI 2)", TEAM_A_GOLD),
            (1, "West (Opponent)" if self.current_mode == "human" else "West (AI 1)", TEAM_B_BLUE),
            (3, "East (Opponent)" if self.current_mode == "human" else "East (AI 3)", TEAM_B_BLUE),
        ]

        for seat_id, name, team_color in seats:
            cx, cy = self.seat_coords[seat_id]
            is_turn = (state.current_player == seat_id and state.phase != Phase.ROUND_OVER and not state.pending_trick_pause)

            # Circle avatar
            border_c = GOLD_BRIGHT if is_turn else team_color
            pygame.draw.circle(self.screen, (22, 32, 26), (cx, cy), 28)
            pygame.draw.circle(self.screen, border_c, (cx, cy), 28, width=2 if not is_turn else 3)

            # Name and cards remaining
            count = len(state.hands[seat_id])
            txt_name = self.font_small.render(name, True, TEXT_WHITE)
            txt_count = self.font_small.render(f"{count} cards", True, TEXT_MUTED)

            nr = txt_name.get_rect(center=(cx, cy + 38))
            cr = txt_count.get_rect(center=(cx, cy + 52))
            self.screen.blit(txt_name, nr)
            self.screen.blit(txt_count, cr)

            # Bidding speech bubble
            if state.phase == Phase.BIDDING and seat_id in state.player_bids:
                bid_str = state.player_bids[seat_id]
                if bid_str:
                    b_rect = pygame.Rect(cx - 35, cy - 54, 70, 22)
                    pygame.draw.rect(self.screen, (255, 255, 255), b_rect, border_radius=6)
                    txt_b = self.font_small.render(bid_str, True, (15, 20, 16))
                    self.screen.blit(txt_b, txt_b.get_rect(center=b_rect.center))

    def _draw_scoreboards(self):
        state = self.controller.state
        t0_pts = state.round_points[0]
        t1_pts = state.round_points[1]

        # Team B (Left)
        r_b = pygame.Rect(80, WIN_HEIGHT // 2 - 45, 140, 90)
        pygame.draw.rect(self.screen, CHARCOAL_PANEL, r_b, border_radius=8)
        pygame.draw.rect(self.screen, TEAM_B_BLUE, r_b, width=2, border_radius=8)
        txt_tb = self.font_small.render("TEAM B (DEFENDING)", True, TEAM_B_BLUE)
        txt_pts_b = self.font_large.render(f"{t1_pts} / 29", True, TEXT_WHITE)
        txt_sub_b = self.font_small.render("Card points collected", True, TEXT_MUTED)
        self.screen.blit(txt_tb, (r_b.x + 10, r_b.y + 10))
        self.screen.blit(txt_pts_b, (r_b.x + 10, r_b.y + 28))
        self.screen.blit(txt_sub_b, (r_b.x + 10, r_b.y + 66))

        # Team A (Right)
        r_a = pygame.Rect(WIN_WIDTH - 220, WIN_HEIGHT // 2 - 45, 140, 90)
        pygame.draw.rect(self.screen, CHARCOAL_PANEL, r_a, border_radius=8)
        pygame.draw.rect(self.screen, TEAM_A_GOLD, r_a, width=2, border_radius=8)
        txt_ta = self.font_small.render("TEAM A (DECLARING)", True, TEAM_A_GOLD)
        txt_pts_a = self.font_large.render(f"{t0_pts} / 29", True, TEXT_WHITE)
        txt_sub_a = self.font_small.render("Card points collected", True, TEXT_MUTED)
        self.screen.blit(txt_ta, (r_a.x + 10, r_a.y + 10))
        self.screen.blit(txt_pts_a, (r_a.x + 10, r_a.y + 28))
        self.screen.blit(txt_sub_a, (r_a.x + 10, r_a.y + 66))

        # Match Score (Center Bottom)
        txt_match = self.font_main.render(f"MATCH SCORE: {state.game_points[0]} - {state.game_points[1]} (First to 6)", True, GOLD_BRIGHT)
        mr = txt_match.get_rect(center=(WIN_WIDTH // 2, WIN_HEIGHT - 170))
        self.screen.blit(txt_match, mr)

    def _draw_trick_area(self):
        state = self.controller.state

        # Empty slots outline
        for seat_id, (x, y) in self.trick_coords.items():
            r = pygame.Rect(x - CARD_WIDTH // 2, y - CARD_HEIGHT // 2, CARD_WIDTH, CARD_HEIGHT)
            pygame.draw.rect(self.screen, (20, 48, 32), r, width=1, border_radius=6)

        # Draw cards played in current trick
        if state.current_trick and state.current_trick.cards:
            for pc in state.current_trick.cards:
                seat = pc.player_id
                x, y = self.trick_coords[seat]
                surf = self.asset_mgr.get_card(pc.card.code)
                r = surf.get_rect(center=(x, y))
                self.screen.blit(surf, r)

        # Trick Winner Banner if pause
        if state.pending_trick_pause and state.last_completed_trick:
            win_name = state.last_completed_trick["winner_name"]
            pts = state.last_completed_trick["points"]
            b_rect = pygame.Rect(WIN_WIDTH // 2 - 180, WIN_HEIGHT // 2 - 25, 360, 50)
            pygame.draw.rect(self.screen, (15, 22, 18), b_rect, border_radius=10)
            pygame.draw.rect(self.screen, GOLD_BRIGHT, b_rect, width=2, border_radius=10)
            t_win = self.font_main.render(f"{win_name.upper()} WINS TRICK (+{pts} PTS)", True, GOLD_BRIGHT)
            t_sub = self.font_small.render("Click anywhere to collect trick", True, TEXT_MUTED)
            self.screen.blit(t_win, t_win.get_rect(center=(WIN_WIDTH // 2, WIN_HEIGHT // 2 - 8)))
            self.screen.blit(t_sub, t_sub.get_rect(center=(WIN_WIDTH // 2, WIN_HEIGHT // 2 + 12)))

    def _draw_table_trump_card(self):
        state = self.controller.state
        if state.phase in (Phase.DEALING_1, Phase.BIDDING):
            return

        tx = WIN_WIDTH // 2 - 200
        ty = WIN_HEIGHT // 2 - CARD_HEIGHT // 2
        card_rect = pygame.Rect(tx, ty, CARD_WIDTH, CARD_HEIGHT)
        is_bidder = (state.highest_bidder == 0 and self.current_mode == "human")

        if state.trump_revealed and state.trump_suit:
            # Revealed trump card
            if state.is_seventh_card_trump and state.seventh_card:
                surf = self.asset_mgr.get_card(state.seventh_card.code)
                self.screen.blit(surf, card_rect)
            elif state.trump_card:
                surf = self.asset_mgr.get_card(state.trump_card.code)
                self.screen.blit(surf, card_rect)
            else:
                pygame.draw.rect(self.screen, (240, 240, 245), card_rect, border_radius=6)
                s_txt = self.font_title.render(state.trump_suit.symbol, True, (180, 20, 20) if state.trump_suit in (Suit.HEARTS, Suit.DIAMONDS) else (20, 20, 20))
                self.screen.blit(s_txt, s_txt.get_rect(center=card_rect.center))
            pygame.draw.rect(self.screen, GOLD_BRIGHT, card_rect, width=2, border_radius=6)
            lbl = self.font_small.render("TRUMP (REV)", True, GOLD_BRIGHT)
            self.screen.blit(lbl, lbl.get_rect(center=(card_rect.centerx, card_rect.bottom + 12)))
        elif state.is_seventh_card_trump:
            if is_bidder and state.seventh_card:
                # Bidder knows the 7th card trump immediately
                surf = self.asset_mgr.get_card(state.seventh_card.code)
                self.screen.blit(surf, card_rect)
                pygame.draw.rect(self.screen, (96, 165, 250), card_rect, width=2, border_radius=6)
                lbl = self.font_small.render("YOUR 7TH", True, (147, 197, 253))
                self.screen.blit(lbl, lbl.get_rect(center=(card_rect.centerx, card_rect.bottom + 12)))
            else:
                # Opponents and spectators only see face-down 7th card
                back_surf = self.asset_mgr.get_back()
                self.screen.blit(back_surf, card_rect)
                pygame.draw.rect(self.screen, (59, 130, 246), card_rect, width=2, border_radius=6)
                lbl = self.font_small.render("7TH (SECRET)", True, (147, 197, 253))
                self.screen.blit(lbl, lbl.get_rect(center=(card_rect.centerx, card_rect.bottom + 12)))
        else:
            if is_bidder and state.trump_card:
                surf = self.asset_mgr.get_card(state.trump_card.code)
                self.screen.blit(surf, card_rect)
                pygame.draw.rect(self.screen, GOLD_BRIGHT, card_rect, width=2, border_radius=6)
                lbl = self.font_small.render("YOUR TRUMP", True, GOLD_BRIGHT)
                self.screen.blit(lbl, lbl.get_rect(center=(card_rect.centerx, card_rect.bottom + 12)))
            else:
                back_surf = self.asset_mgr.get_back()
                self.screen.blit(back_surf, card_rect)
                pygame.draw.rect(self.screen, GOLD_TRIM, card_rect, width=2, border_radius=6)
                lbl = self.font_small.render("SECRET TRUMP", True, TEXT_MUTED)
                self.screen.blit(lbl, lbl.get_rect(center=(card_rect.centerx, card_rect.bottom + 12)))

    def _draw_human_hand(self):
        state = self.controller.state
        hand = state.hands[0]
        n = len(hand)
        if n == 0:
            return

        spacing = 65
        total_w = (n - 1) * spacing + CARD_WIDTH
        start_x = (WIN_WIDTH - total_w) // 2
        base_y = WIN_HEIGHT - CARD_HEIGHT - 15

        legal_cards = Rules.get_legal_cards(0, state) if (state.phase == Phase.PLAYING and self.controller.is_human_turn()) else []

        for i, card in enumerate(hand):
            x = start_x + i * spacing
            is_hovered = (i == self.hovered_card_idx)
            y = base_y - (20 if is_hovered else 0)

            surf = self.asset_mgr.get_card(card.code)
            self.screen.blit(surf, (x, y))

            # Gold border if legal and human turn
            if state.phase == Phase.PLAYING and self.controller.is_human_turn():
                if card in legal_cards:
                    pygame.draw.rect(self.screen, GOLD_BRIGHT, pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT), width=2, border_radius=10)
                else:
                    # Subtle dim for illegal card
                    dim_surf = pygame.Surface((CARD_WIDTH, CARD_HEIGHT), pygame.SRCALPHA)
                    dim_surf.fill((0, 0, 0, 100))
                    self.screen.blit(dim_surf, (x, y))

    def _draw_modals(self):
        state = self.controller.state

        # 0. Deal Abandoned Modal
        if state.deal_abandoned:
            self._draw_deal_abandoned_modal()

        # 1. Bidding Modal
        elif state.phase == Phase.BIDDING and self.controller.is_human_turn() and self.current_mode == "human":
            self._draw_bidding_modal()

        # 2. Trump Selection Modal
        elif state.phase == Phase.TRUMP_SELECTION and self.controller.is_human_turn() and self.current_mode == "human":
            self._draw_trump_selection_modal()

        # 3. Round Result Modal
        elif state.phase == Phase.ROUND_OVER:
            self._draw_round_over_modal()

        # 4. Rules Screen Overlay
        elif self.show_rules:
            self._draw_rules_overlay()

        # 5. Inspector Overlay
        elif self.show_inspector:
            self._draw_inspector_overlay()

    def _draw_deal_abandoned_modal(self):
        modal_rect = pygame.Rect(WIN_WIDTH // 2 - 250, WIN_HEIGHT // 2 - 120, 500, 240)
        pygame.draw.rect(self.screen, (32, 12, 14), modal_rect, border_radius=12)
        pygame.draw.rect(self.screen, (239, 68, 68), modal_rect, width=2, border_radius=12)

        txt_tag = self.font_small.render("AUTHENTIC 29 RULE", True, (248, 113, 113))
        self.screen.blit(txt_tag, txt_tag.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 24)))

        txt_title = self.font_title.render("MATCH / DEAL ABANDONED", True, (255, 90, 90))
        self.screen.blit(txt_title, txt_title.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 54)))

        msg = self.controller.state.abandon_reason or "Declarer has no point cards in trump suit! Deal is void."
        txt_desc = self.font_small.render(msg[:62], True, (254, 202, 202))
        self.screen.blit(txt_desc, txt_desc.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 95)))
        if len(msg) > 62:
            txt_desc2 = self.font_small.render(msg[62:125], True, (254, 202, 202))
            self.screen.blit(txt_desc2, txt_desc2.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 118)))

        txt_btn = self.font_main.render("CLICK ANYWHERE TO START NEXT DEAL", True, (255, 255, 255))
        self.screen.blit(txt_btn, txt_btn.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 175)))

    def _draw_bidding_modal(self):
        state = self.controller.state
        modal_rect = pygame.Rect(WIN_WIDTH // 2 - 180, WIN_HEIGHT // 2 - 110, 360, 220)
        pygame.draw.rect(self.screen, CHARCOAL_PANEL, modal_rect, border_radius=12)
        pygame.draw.rect(self.screen, GOLD_TRIM, modal_rect, width=2, border_radius=12)

        txt_title = self.font_title.render("PLACE YOUR BID", True, GOLD_BRIGHT)
        self.screen.blit(txt_title, txt_title.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 24)))

        curr = state.bid if state.bid > 0 else "None"
        txt_curr = self.font_small.render(f"Current highest bid: {curr}", True, TEXT_MUTED)
        self.screen.blit(txt_curr, txt_curr.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 50)))

        # Bidding Buttons
        min_bid = max(16, state.bid + 1)
        self.bidding_buttons = []
        col_w = 60
        btn_y = modal_rect.y + 80

        # Generate chips: min, min+1, min+2, 20, 24
        chip_vals = [min_bid]
        if min_bid + 1 <= 28: chip_vals.append(min_bid + 1)
        if min_bid + 2 <= 28: chip_vals.append(min_bid + 2)
        if 20 >= min_bid and 20 not in chip_vals: chip_vals.append(20)

        for idx, val in enumerate(chip_vals[:4]):
            bx = modal_rect.x + 24 + idx * 78
            btn = Button(pygame.Rect(bx, btn_y, 70, 38), f"{val} Bid", bg_color=(34, 52, 40))
            self.bidding_buttons.append(btn)
            btn.draw(self.screen, self.font_small)

        # PASS button
        pass_btn = Button(pygame.Rect(WIN_WIDTH // 2 - 60, modal_rect.y + 145, 120, 36), "PASS", bg_color=(120, 25, 25), border_color=(255, 100, 100))
        self.bidding_buttons.append(pass_btn)
        pass_btn.draw(self.screen, self.font_main)

    def _draw_trump_selection_modal(self):
        modal_rect = pygame.Rect(WIN_WIDTH // 2 - 270, WIN_HEIGHT // 2 - 160, 540, 320)
        pygame.draw.rect(self.screen, CHARCOAL_PANEL, modal_rect, border_radius=12)
        pygame.draw.rect(self.screen, GOLD_TRIM, modal_rect, width=2, border_radius=12)

        txt_title = self.font_title.render("SELECT TRUMP OPTION", True, GOLD_BRIGHT)
        self.screen.blit(txt_title, txt_title.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 24)))

        txt_desc = self.font_small.render("Choose one of 4 suits or the 7th-Card rule (Points: J=3, 9=2, A=1, 10=1):", True, TEXT_MUTED)
        self.screen.blit(txt_desc, txt_desc.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 48)))

        # 5 Trump Option Buttons
        self.trump_buttons = []
        options = [
            ("SPADES", "♠ Spades", (20, 30, 24)),
            ("HEARTS", "♥ Hearts", (40, 20, 24)),
            ("CLUBS", "♣ Clubs", (20, 30, 24)),
            ("DIAMONDS", "♦ Diamonds", (40, 20, 24)),
            ("SEVENTH_CARD", "🃏 7th Card", (15, 30, 55))
        ]
        btn_y = modal_rect.y + 70
        btn_w = 96
        start_bx = modal_rect.x + (modal_rect.width - (5 * btn_w + 4 * 8)) // 2

        for i, (opt_val, opt_label, bg_col) in enumerate(options):
            bx = start_bx + i * (btn_w + 8)
            rect = pygame.Rect(bx, btn_y, btn_w, 36)
            self.trump_buttons.append((rect, opt_val))
            pygame.draw.rect(self.screen, bg_col, rect, border_radius=6)
            border_col = (96, 165, 250) if opt_val == "SEVENTH_CARD" else GOLD_TRIM
            pygame.draw.rect(self.screen, border_col, rect, width=1, border_radius=6)
            txt = self.font_small.render(opt_label, True, TEXT_WHITE)
            self.screen.blit(txt, txt.get_rect(center=rect.center))

        txt_ref = self.font_small.render("— Or click a card from your current hand —", True, (150, 170, 160))
        self.screen.blit(txt_ref, txt_ref.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 125)))

        # 4 cards drawn horizontally
        hand = self.controller.state.hands[0]
        spacing = 90
        start_x = (WIN_WIDTH - (len(hand) * spacing)) // 2
        cy = modal_rect.y + 215

        self.trump_card_rects = []
        for i, card in enumerate(hand):
            x = start_x + i * spacing
            card_rect = pygame.Rect(x, cy - 58, 80, 116)
            self.trump_card_rects.append((card_rect, card))
            surf = self.asset_mgr.get_card(card.code)
            surf_small = pygame.transform.smoothscale(surf, (80, 116))
            self.screen.blit(surf_small, (x, cy - 58))
            pygame.draw.rect(self.screen, GOLD_TRIM, card_rect, width=1, border_radius=6)

    def _draw_round_over_modal(self):
        state = self.controller.state
        modal_rect = pygame.Rect(WIN_WIDTH // 2 - 220, WIN_HEIGHT // 2 - 120, 440, 240)
        pygame.draw.rect(self.screen, CHARCOAL_PANEL, modal_rect, border_radius=12)
        pygame.draw.rect(self.screen, GOLD_TRIM, modal_rect, width=2, border_radius=12)

        target = state.target_bid if state.target_bid > 0 else state.bid
        bidder_team = state.get_team(state.highest_bidder) if state.highest_bidder is not None else 0
        bidder_pts = state.round_points[bidder_team]
        success = bidder_pts >= target

        t_color = (0, 255, 136) if success else (255, 80, 80)
        txt_res = self.font_large.render("CONTRACT MADE!" if success else "CONTRACT FAILED!", True, t_color)
        self.screen.blit(txt_res, txt_res.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 35)))

        txt_detail = self.font_main.render(f"Team {chr(65+bidder_team)} collected {bidder_pts} / 29 pts (Target: {target})", True, TEXT_WHITE)
        self.screen.blit(txt_detail, txt_detail.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 80)))

        txt_match = self.font_small.render(f"Match Points: Team A: {state.game_points[0]}  |  Team B: {state.game_points[1]}", True, GOLD_BRIGHT)
        self.screen.blit(txt_match, txt_match.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 115)))

        txt_click = self.font_main.render("CLICK ANYWHERE FOR NEXT HAND", True, (255, 255, 255))
        self.screen.blit(txt_click, txt_click.get_rect(center=(WIN_WIDTH // 2, modal_rect.y + 175)))

    def _draw_rules_overlay(self):
        r = pygame.Rect(120, 60, WIN_WIDTH - 240, WIN_HEIGHT - 120)
        pygame.draw.rect(self.screen, (15, 22, 18), r, border_radius=12)
        pygame.draw.rect(self.screen, GOLD_TRIM, r, width=2, border_radius=12)

        txt_t = self.font_title.render("29 CARD GAME — RULES & SCORING REFERENCE", True, GOLD_BRIGHT)
        self.screen.blit(txt_t, (r.x + 24, r.y + 20))

        lines = [
            "• Deck: 32 cards (J, 9, A, 10, K, Q, 8, 7 in each of 4 suits).",
            "• Card Point Values: J = 3 pts,  9 = 2 pts,  A = 1 pt,  10 = 1 pt.  (K, Q, 8, 7 = 0 pts).",
            "• Total Deck Points = 28. Final 8th trick winner gets +1 bonus point = 29 Total Points.",
            "• Power Hierarchy: J > 9 > A > 10 > K > Q > 8 > 7.",
            "• Bidding: Auction from 16 to 28. Declarer secretly sets trump card.",
            "• Trump Reveal: Can be revealed when player is void in the led suit.",
            "• Royal Pair: Holding K & Q of trump: Bidding team -4 target; Defending team +4 target.",
            "• Press ESC to close this rules window."
        ]
        for idx, line in enumerate(lines):
            t = self.font_small.render(line, True, TEXT_WHITE)
            self.screen.blit(t, (r.x + 24, r.y + 65 + idx * 32))

    def _draw_inspector_overlay(self):
        r = pygame.Rect(120, 60, WIN_WIDTH - 240, WIN_HEIGHT - 120)
        pygame.draw.rect(self.screen, (15, 22, 18), r, border_radius=12)
        pygame.draw.rect(self.screen, GOLD_TRIM, r, width=2, border_radius=12)

        txt_t = self.font_title.render("AI STRATEGIC DECISION INSPECTOR", True, GOLD_BRIGHT)
        self.screen.blit(txt_t, (r.x + 24, r.y + 20))

        stats = self.controller.stats
        rounds = stats["rounds_played"]
        win_a = round((stats["team_a_wins"] / rounds * 100), 1) if rounds > 0 else 0
        win_b = round((stats["team_b_wins"] / rounds * 100), 1) if rounds > 0 else 0

        lines = [
            f"• Hands Completed: {rounds}",
            f"• Team A Win Rate: {win_a}%   |   Team B Win Rate: {win_b}%",
            f"• Contracts Fulfilled: {stats['contracts_made']} / {stats['contracts_attempted']}",
            "",
            "Latest AI Reasoning & Strategy Output:",
            f"  {self.controller.state.latest_insight or 'Awaiting AI decisions...'}",
            "",
            "Architecture Layers:",
            "  1. 4-Input Mamdani Fuzzy Inference (Strength, Trump Potential, Support, Uncertainty)",
            "  2. Monte Carlo Expected Utility Bidding with CRN (Common Random Numbers)",
            "  3. Information Set MCTS (Strategic hidden-deal midgame search)",
            "  4. Alpha-Beta Minimax (Exact endgame trick solver)",
            "",
            "• Press ESC to return to table."
        ]
        for idx, line in enumerate(lines):
            t = self.font_small.render(line, True, TEXT_WHITE if not line.startswith("Latest") else GOLD_BRIGHT)
            self.screen.blit(t, (r.x + 24, r.y + 60 + idx * 24))

def launch_pygame_app(human_mode: bool = True):
    app = PygameApp(human_mode=human_mode)
    app.run()

if __name__ == "__main__":
    launch_pygame_app()
