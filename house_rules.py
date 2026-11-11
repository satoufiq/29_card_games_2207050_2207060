"""
Configurable house rules for Intelligent 29 Cards Game.

Local conventions differ from table to table, so every rule that has more than
one common interpretation lives here and is chosen before a match starts.
Nothing in the engine silently assumes one interpretation of Single Hand.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass
class SingleHandRules:
    # Master switch. When False the Single Hand call is never offered.
    enabled: bool = True
    # When the call can be made:
    #   "after_deal" - after all 8 cards are dealt, before the first lead (classic)
    #   "auction"    - as a special call during the 4-card auction (outranks any number)
    timing: str = "after_deal"
    # Declarer's partner lays the hand face down and does not play (3-card tricks).
    partner_sits_out: bool = True
    # Only relevant when the partner plays: do tricks won by the partner count
    # as tricks won for the Single Hand?
    partner_tricks_count: bool = False
    # Declarer (or the team, if partner tricks count) must win all 8 tricks.
    must_win_all_tricks: bool = True
    # Declarer must also reach the normal contract target in card points.
    use_contract_target: bool = False
    # Trump in a Single Hand: "none" (no trump) or "declarer_chooses" (named openly).
    trump: str = "none"
    # Match points won / lost.
    win_points: int = 3
    loss_points: int = 3

    def win_condition_text(self) -> str:
        parts = []
        if self.must_win_all_tricks or not self.use_contract_target:
            who = "the team" if (not self.partner_sits_out and self.partner_tricks_count) else "the declarer"
            parts.append(f"{who} must win all 8 tricks")
        if self.use_contract_target:
            parts.append("card points must reach the contract target")
        return " and ".join(parts)


@dataclass
class HouseRules:
    # +1 card point for the last trick (29-point game). False = pure 28 card points.
    last_trick_bonus: bool = False
    # What happens when all four players pass without a bid:
    #   "dealer_forced" - dealer must play at 16
    #   "redeal"        - cards are thrown in and the next dealer deals
    all_pass_rule: str = "dealer_forced"
    # Lowest legal bid and highest legal bid.
    min_bid: int = 16
    max_bid: int = 28
    # Bidder may choose the concealed 7th card as trump.
    allow_seventh_card: bool = True
    # Royal marriage (K + Q of trump).
    marriage_enabled: bool = True
    #   "auto"        - applied automatically the moment trump is revealed
    #   "after_trick" - holder announces it after their team wins a trick post-reveal
    marriage_mode: str = "auto"
    marriage_value: int = 4
    # Defenders may double, declarers may redouble.
    double_redouble: bool = True
    # Match ends when a team reaches +target or -target match points.
    match_target: int = 6
    single_hand: SingleHandRules = field(default_factory=SingleHandRules)

    @property
    def game_variant(self) -> str:
        return "29" if self.last_trick_bonus else "28"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["single_hand"]["win_condition_text"] = self.single_hand.win_condition_text()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HouseRules":
        data = dict(data or {})
        sh_data = dict(data.pop("single_hand", {}) or {})
        sh_data.pop("win_condition_text", None)
        sh = SingleHandRules()
        for k, v in sh_data.items():
            if hasattr(sh, k):
                setattr(sh, k, type(getattr(sh, k))(v))
        hr = cls(single_hand=sh)
        for k, v in data.items():
            if hasattr(hr, k) and k != "single_hand":
                setattr(hr, k, type(getattr(hr, k))(v))
        hr.validate()
        return hr

    def validate(self):
        if self.all_pass_rule not in ("dealer_forced", "redeal"):
            self.all_pass_rule = "dealer_forced"
        if self.marriage_mode not in ("auto", "after_trick"):
            self.marriage_mode = "auto"
        self.min_bid = max(14, min(20, self.min_bid))
        self.max_bid = max(self.min_bid + 1, min(29 if self.last_trick_bonus else 28, self.max_bid))
        self.match_target = max(1, min(12, self.match_target))
        sh = self.single_hand
        if sh.timing not in ("after_deal", "auction"):
            sh.timing = "after_deal"
        if sh.trump not in ("none", "declarer_chooses"):
            sh.trump = "none"
        sh.win_points = max(1, min(12, sh.win_points))
        sh.loss_points = max(1, min(12, sh.loss_points))
        if not sh.must_win_all_tricks and not sh.use_contract_target:
            # A Single Hand needs some win condition; default to the classic one.
            sh.must_win_all_tricks = True
