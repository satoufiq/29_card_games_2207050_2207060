"""
Fast simulation core shared by ISMCTS, endgame minimax, bidding and
Single Hand / doubling estimators.

Important for fairness: the only entry point that creates a full deal for an
AI is `sample_world`, which works from the AI's masked view (own hand +
public information + inferred voids). Hidden cards are never read from the
real game state.
"""
import random
from typing import List, Optional, Tuple, Dict, Set
from card import Card, Suit, Rank
from game_state import GameState

ALL_CARDS: List[Card] = [Card(suit=s, rank=r) for s in Suit for r in Rank]
POWER: Dict[Card, int] = {c: c.rank.power for c in ALL_CARDS}
POINTS: Dict[Card, int] = {c: c.rank.points for c in ALL_CARDS}
SUIT_CARDS: Dict[Suit, List[Card]] = {
    s: sorted([c for c in ALL_CARDS if c.suit == s], key=lambda c: -POWER[c]) for s in Suit
}


def team_of(p: int) -> int:
    return 0 if p in (0, 2) else 1


class SimState:
    """Lightweight mutable game for rollouts. Trick entries are (player, card)."""
    __slots__ = ("hands", "trick", "current", "trump", "revealed", "sitting_out",
                 "pts", "tricks_won", "done", "bonus", "played", "bidder",
                 "target", "single_hand", "trick_log", "size")

    def __init__(self, hands, trick, current, trump, revealed, sitting_out,
                 pts, tricks_won, done, bonus, played, bidder, target, single_hand):
        self.hands = hands
        self.trick = trick
        self.current = current
        self.trump = trump
        self.revealed = revealed
        self.sitting_out = sitting_out
        self.pts = pts
        self.tricks_won = tricks_won
        self.done = done
        self.bonus = bonus
        self.played = played
        self.bidder = bidder
        self.target = target
        self.single_hand = single_hand
        self.trick_log = []     # list of (winner, points) for tricks completed inside the sim
        self.size = 3 if sitting_out is not None else 4

    def clone(self) -> "SimState":
        s = SimState([list(h) for h in self.hands], list(self.trick), self.current, self.trump,
                     self.revealed, self.sitting_out, list(self.pts), list(self.tricks_won),
                     self.done, self.bonus, set(self.played), self.bidder, self.target, self.single_hand)
        s.trick_log = list(self.trick_log)
        return s

    def next_player(self, p: int) -> int:
        n = (p + 1) % 4
        if n == self.sitting_out:
            n = (n + 1) % 4
        return n

    def is_terminal(self) -> bool:
        if self.done >= 8:
            return True
        cur = self.hands[self.current]
        return not cur and not self.trick

    def legal(self, p: int) -> List[Card]:
        hand = self.hands[p]
        if not self.trick:
            return list(hand)
        lead = self.trick[0][1].suit
        same = [c for c in hand if c.suit is lead]
        return same if same else list(hand)

    def current_winner(self) -> Tuple[int, Card, bool]:
        """(player, card, is_trump_win) for the trick so far."""
        lead = self.trick[0][1].suit
        trump = self.trump if self.revealed else None
        best_p, best_c = self.trick[0]
        best_t = trump is not None and best_c.suit is trump
        for p, c in self.trick[1:]:
            ct = trump is not None and c.suit is trump
            if ct and not best_t:
                best_p, best_c, best_t = p, c, True
            elif ct == best_t and (ct or c.suit is lead) and (c.suit is best_c.suit) and POWER[c] > POWER[best_c]:
                best_p, best_c = p, c
        return best_p, best_c, best_t

    def play(self, card: Card, allow_reveal: bool = True):
        p = self.current
        self.hands[p].remove(card)
        if (allow_reveal and not self.revealed and self.trump is not None and self.trick
                and card.suit is self.trump and card.suit is not self.trick[0][1].suit):
            # A void player calls for the trump and ruffs.
            self.revealed = True
        self.trick.append((p, card))
        self.played.add(card)
        if len(self.trick) >= self.size:
            winner, _, _ = self.current_winner()
            pts = 0
            for _, c in self.trick:
                pts += POINTS[c]
            self.done += 1
            if self.done == 8 and self.bonus:
                pts += 1
            self.pts[team_of(winner)] += pts
            self.tricks_won[winner] += 1
            self.trick_log.append((winner, pts))
            self.trick = []
            self.current = winner
        else:
            self.current = self.next_player(p)

    def is_boss(self, card: Card, hand: List[Card]) -> bool:
        """True if no unplayed card outside `hand` beats `card` in its own suit."""
        pw = POWER[card]
        for c in SUIT_CARDS[card.suit]:
            if POWER[c] <= pw:
                return True
            if c not in self.played and c not in hand:
                return False
        return True


# ---------------------------------------------------------------- rollout policy
def heuristic_card(sim: SimState, rng: random.Random, epsilon: float = 0.08) -> Card:
    """Partnership-aware rollout policy used for every simulated player."""
    p = sim.current
    legal = sim.legal(p)
    if len(legal) == 1:
        return legal[0]
    if rng.random() < epsilon:
        return rng.choice(legal)
    hand = sim.hands[p]
    trump = sim.trump
    declarer_side = sim.single_hand and team_of(p) == team_of(sim.bidder)

    if not sim.trick:
        # Leading: cash a boss card, else lead low from a non-trump suit.
        if sim.revealed and trump is not None and team_of(p) == team_of(sim.bidder if sim.bidder is not None else p):
            trumps = [c for c in legal if c.suit is trump]
            if len(trumps) >= 2 and sim.is_boss(max(trumps, key=POWER.get), hand):
                return max(trumps, key=POWER.get)
        bosses = [c for c in legal if (c.suit is not trump or not sim.revealed) and sim.is_boss(c, hand)]
        if bosses:
            return max(bosses, key=lambda c: (POINTS[c], POWER[c]))
        if declarer_side:
            return max(legal, key=POWER.get)
        pool = [c for c in legal if c.suit is not trump] or legal
        return min(pool, key=lambda c: (POINTS[c], POWER[c]))

    lead = sim.trick[0][1].suit
    w_p, w_c, w_t = sim.current_winner()
    last_to_play = len(sim.trick) == sim.size - 1
    in_suit = legal[0].suit is lead
    on_table = sum(POINTS[c] for _, c in sim.trick)

    if team_of(w_p) == team_of(p):
        # Partner is winning: smear points if the win looks safe, else play low.
        safe = last_to_play or w_t or sim.is_boss(w_c, hand)
        if safe:
            pool = [c for c in legal if not (sim.revealed and c.suit is trump)] or legal
            return max(pool, key=lambda c: (POINTS[c], -POWER[c]))
        return min(legal, key=lambda c: (POINTS[c], POWER[c]))

    if in_suit:
        if not w_t:
            winners = [c for c in legal if POWER[c] > POWER[w_c]]
            if winners:
                cheapest = min(winners, key=POWER.get)
                if last_to_play or sim.is_boss(cheapest, hand) or on_table + POINTS[cheapest] >= 2:
                    return cheapest
        return min(legal, key=lambda c: (POINTS[c], POWER[c]))

    # Void in lead suit
    if trump is not None:
        trumps = [c for c in legal if c.suit is trump]
        if trumps and (on_table >= 1 or sim.done >= 5 or declarer_side or rng.random() < 0.25):
            if w_t:
                over = [c for c in trumps if POWER[c] > POWER[w_c]]
                if over:
                    return min(over, key=POWER.get)
            else:
                return min(trumps, key=POWER.get)
    pool = [c for c in legal if c.suit is not trump] or legal
    return min(pool, key=lambda c: (POINTS[c], POWER[c]))


def rollout(sim: SimState, rng: random.Random, epsilon: float = 0.08):
    guard = 0
    while not sim.is_terminal() and guard < 40:
        if not sim.hands[sim.current]:
            break
        sim.play(heuristic_card(sim, rng, epsilon))
        guard += 1


# ---------------------------------------------------------------- outcomes
def contract_made(sim: SimState) -> bool:
    if sim.bidder is None:
        return False
    if sim.single_hand:
        return sim.tricks_won[sim.bidder] >= sim.done and sim.done > 0
    return sim.pts[team_of(sim.bidder)] >= sim.target


def neutral_team_value(sim: SimState, team: int) -> float:
    total = max(1, sim.pts[0] + sim.pts[1])
    share = sim.pts[team] / total
    if sim.bidder is None:
        return share
    made = contract_made(sim)
    good = made if team == team_of(sim.bidder) else not made
    return 0.6 * (1.0 if good else 0.0) + 0.4 * share


# ---------------------------------------------------------------- world sampling
def _public_played(ms: GameState) -> Set[Card]:
    played = set()
    for t in ms.completed_tricks:
        for pc in t.cards:
            played.add(pc.card)
    if ms.current_trick:
        for pc in ms.current_trick.cards:
            played.add(pc.card)
    return played


def public_voids(ms: GameState, kb=None) -> Set[Tuple[int, Suit]]:
    voids = set(kb.void_facts) if kb is not None else set()
    tricks = list(ms.completed_tricks)
    if ms.current_trick and ms.current_trick.cards:
        tricks.append(ms.current_trick)
    for t in tricks:
        lead = t.lead_suit
        for i, pc in enumerate(t.cards):
            if i > 0 and lead is not None and pc.card.suit != lead:
                voids.add((pc.player_id, lead))
    return voids


def known_trump_for(viewer: int, ms: GameState, kb=None) -> Tuple[Optional[Suit], bool]:
    """(trump suit if known to viewer, whether it is known)."""
    if ms.single_hand:
        return ms.trump_suit, True
    if ms.trump_revealed and ms.trump_suit is not None:
        return ms.trump_suit, True
    if viewer == ms.highest_bidder and ms.trump_suit is not None:
        return ms.trump_suit, True
    if kb is not None and kb.known_trump is not None:
        return kb.known_trump, True
    return None, False


def trump_hypothesis_weights(viewer: int, ms: GameState, unseen: List[Card], voids) -> Dict[Suit, float]:
    """Belief over the hidden trump suit: the bidder needs trump point cards, so
    suits with many unseen point cards are likelier; suits the bidder has shown
    void in are impossible."""
    bidder = ms.highest_bidder
    w = {}
    for s in Suit:
        if bidder is not None and (bidder, s) in voids:
            w[s] = 0.0
            continue
        pts_cards = sum(1 for c in unseen if c.suit is s and POINTS[c] > 0)
        n = sum(1 for c in unseen if c.suit is s)
        w[s] = (pts_cards + 0.4 * n) if n else 0.0
    if sum(w.values()) <= 0:
        w = {s: 1.0 for s in Suit}
    return w


def sample_world(viewer: int, ms: GameState, kb=None, rng: Optional[random.Random] = None,
                 attempts: int = 10) -> Tuple[List[List[Card]], Optional[Suit]]:
    """
    Samples a full deal consistent with everything `viewer` knows:
      * own hand (plus the concealed 7th card if the viewer set it),
      * public plays, hand sizes, and VoidInSuit(p, s) facts,
      * a hypothesis for an unrevealed trump suit (bidder must hold trump points).
    Returns (hands, trump_suit_for_this_world).
    """
    rng = rng or random.Random()
    sizes = ms.hand_sizes()
    own = list(ms.hands[viewer])
    seventh_hidden = ms.is_seventh_card_trump and not ms.trump_revealed and ms.highest_bidder is not None
    if seventh_hidden and viewer == ms.highest_bidder and ms.seventh_card is not None:
        own.append(ms.seventh_card)   # it returns to the bidder's hand on reveal
    played = _public_played(ms)
    own_set = set(own)
    unseen = [c for c in ALL_CARDS if c not in played and c not in own_set]
    voids = public_voids(ms, kb)

    trump, known = known_trump_for(viewer, ms, kb)
    bidder = ms.highest_bidder

    need = {p: sizes[p] for p in range(4) if p != viewer}
    reserved: Dict[int, List[Card]] = {p: [] for p in range(4)}
    if not known and bidder is not None and bidder != viewer and not ms.single_hand:
        weights = trump_hypothesis_weights(viewer, ms, unseen, voids)
        suits = list(weights.keys())
        trump = rng.choices(suits, weights=[weights[s] for s in suits])[0]
        if seventh_hidden:
            cands = [c for c in unseen if c.suit is trump]
            if cands:
                c7 = rng.choice(cands)
                reserved[bidder].append(c7)
                unseen.remove(c7)
    elif seventh_hidden and bidder is not None and bidder != viewer:
        # Trump known (e.g. bidder's partner told by reveal elsewhere): give one card back.
        need[bidder] = need.get(bidder, 0) + 1

    best = None
    for attempt in range(attempts):
        pool = list(unseen)
        rng.shuffle(pool)
        hands = [[] for _ in range(4)]
        hands[viewer] = list(own)
        for p in reserved:
            hands[p].extend(reserved[p])
        order = sorted(need.keys(), key=lambda p: -sum(1 for (q, _) in voids if q == p))
        ok = True
        for p in order:
            want = need[p]
            elig = [c for c in pool if (p, c.suit) not in voids]
            if len(elig) < want:
                ok = False
                elig = elig + [c for c in pool if c not in elig]
            take = elig[:want]
            hands[p].extend(take)
            for c in take:
                pool.remove(c)
        if (ok and trump is not None and not known and bidder is not None and bidder != viewer
                and not any(c.suit is trump and POINTS[c] > 0 for c in hands[bidder])):
            ok = attempt >= attempts - 1
        best = hands
        if ok:
            break
    return best, trump


def build_sim(viewer: int, ms: GameState, hands: List[List[Card]], trump: Optional[Suit]) -> SimState:
    trick = []
    if ms.current_trick and ms.current_trick.cards:
        trick = [(pc.player_id, pc.card) for pc in ms.current_trick.cards]
    played = _public_played(ms)
    bidder = ms.single_hand_declarer if ms.single_hand else ms.highest_bidder
    target = ms.target_bid or ms.bid or ms.rules.min_bid
    revealed = ms.trump_revealed or ms.single_hand
    return SimState(
        hands=[list(h) for h in hands], trick=trick, current=ms.current_player,
        trump=trump, revealed=revealed, sitting_out=ms.sitting_out,
        pts=list(ms.round_points), tricks_won=list(ms.tricks_won),
        done=len(ms.completed_tricks), bonus=ms.rules.last_trick_bonus,
        played=played, bidder=bidder, target=target, single_hand=ms.single_hand,
    )


def estimate_contract(viewer: int, ms: GameState, kb=None, n: int = 60,
                      rng: Optional[random.Random] = None) -> Dict[str, float]:
    """Monte Carlo estimate of P(contract made) from the viewer's information."""
    rng = rng or random.Random()
    made = 0
    pts_sum = 0.0
    bt = team_of(ms.single_hand_declarer if ms.single_hand else ms.highest_bidder) if ms.highest_bidder is not None else 0
    for _ in range(n):
        hands, trump = sample_world(viewer, ms, kb, rng, attempts=4)
        sim = build_sim(viewer, ms, hands, trump)
        rollout(sim, rng, epsilon=0.05)
        if contract_made(sim):
            made += 1
        pts_sum += sim.pts[bt]
    return {"p_made": made / max(1, n), "avg_bidder_points": pts_sum / max(1, n), "samples": n}


def estimate_contract_predeal(viewer: int, ms: GameState, n: int = 60,
                              rng: Optional[random.Random] = None) -> Dict[str, float]:
    """
    P(contract made) while everyone still holds only the first 4 cards (doubling
    happens before the rest is dealt). Each sample completes all four hands from the
    unseen cards. The trump is the bidder's chosen suit if the viewer knows it;
    otherwise a suit in which the sampled bidder holds point cards (the bidder must),
    or the suit of the bidder's sampled 7th card for a 7th-card trump.
    """
    rng = rng or random.Random()
    own = list(ms.hands[viewer])
    bidder = ms.highest_bidder
    bt = team_of(bidder)
    target = ms.target_bid or ms.bid or ms.rules.min_bid
    lead = (ms.dealer + 1) % 4
    known_trump = ms.trump_suit if (viewer == bidder and ms.trump_suit is not None) else None
    made = 0
    pts_sum = 0.0
    for _ in range(n):
        pool = [c for c in ALL_CARDS if c not in own]
        rng.shuffle(pool)
        hands = [[] for _ in range(4)]
        hands[viewer] = own + pool[:8 - len(own)]
        rest = pool[8 - len(own):]
        others = [p for p in range(4) if p != viewer]
        for i, p in enumerate(others):
            hands[p] = rest[i * 8:(i + 1) * 8]
        trump = known_trump
        if trump is None:
            if ms.is_seventh_card_trump:
                trump = hands[bidder][6].suit
            else:
                weights = {s: sum(POINTS[c] + 0.5 for c in hands[bidder][:4] if c.suit is s)
                           for s in Suit}
                suits = [s for s in Suit if weights[s] > 0] or list(Suit)
                trump = rng.choices(suits, weights=[weights.get(s, 1.0) or 1.0 for s in suits])[0]
        sim = SimState(hands=hands, trick=[], current=lead, trump=trump, revealed=False,
                       sitting_out=None, pts=[0, 0], tricks_won=[0, 0, 0, 0], done=0,
                       bonus=ms.rules.last_trick_bonus, played=set(), bidder=bidder,
                       target=target, single_hand=False)
        rollout(sim, rng, epsilon=0.05)
        if contract_made(sim):
            made += 1
        pts_sum += sim.pts[bt]
    return {"p_made": made / max(1, n), "avg_bidder_points": pts_sum / max(1, n), "samples": n}


def estimate_single_hand(viewer: int, ms: GameState, trump_choice: Optional[Suit], partner_sits_out: bool,
                         n: int = 60, rng: Optional[random.Random] = None,
                         extra_unknown_own: int = 0) -> float:
    """
    P(viewer wins every trick alone) if viewer declared a Single Hand now.
    extra_unknown_own > 0 is used during the 4-card auction: the viewer's
    remaining cards are sampled too.
    """
    rng = rng or random.Random()
    own = list(ms.hands[viewer])
    wins = 0
    for _ in range(n):
        pool = [c for c in ALL_CARDS if c not in own]
        rng.shuffle(pool)
        my = own + pool[:extra_unknown_own]
        rest = pool[extra_unknown_own:]
        hands = [[] for _ in range(4)]
        hands[viewer] = my
        others = [(viewer + k) % 4 for k in (1, 2, 3)]
        for i, p in enumerate(others):
            hands[p] = rest[i * 8:(i + 1) * 8]
        trump = trump_choice
        sitting = (viewer + 2) % 4 if partner_sits_out else None
        sim = SimState(hands=hands, trick=[], current=viewer, trump=trump, revealed=True,
                       sitting_out=sitting, pts=[0, 0], tricks_won=[0, 0, 0, 0], done=0,
                       bonus=False, played=set(), bidder=viewer, target=0, single_hand=True)
        while not sim.is_terminal():
            if not sim.hands[sim.current]:
                break
            sim.play(heuristic_card(sim, rng, epsilon=0.0))
            if sim.trick_log and sim.trick_log[-1][0] != viewer:
                break
        if sim.tricks_won[viewer] == 8:
            wins += 1
    return wins / max(1, n)
