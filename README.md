# Intelligent 29 Cards Game

A complete, playable **29** card game (Bangladeshi rules) with three genuinely different AI
personalities — **Aggressive**, **Strategic** and **Defensive** — built on
Information Set Monte Carlo Tree Search, Mamdani fuzzy logic and endgame Minimax,
with a cinematic browser table.

Pure Python standard library on the server and plain HTML/CSS/JS in the browser:
**nothing to install** beyond Python 3.10+.

---

## 1. Quick start

```bash
py main.py
```

**This is the single entry point.** It starts the game and opens
`http://127.0.0.1:8029` in your browser. Any other copy of this game that is
still running (an older version, or a second window) is shut down and replaced
automatically, so there is only ever one game server. If the same version is
already running, it is simply reused. Programs that are not this game are never
touched; if one of them holds port 8029, the next free port is used instead.

| Command | What it does |
|---|---|
| `py main.py` / `py main.py gui` | Web table (recommended) |
| `py main.py serve` | Web server only, no browser |
| `py main.py headless` | One 4-AI round in the console |
| `py main.py personalities` | Experiment showing how the three personalities differ |
| `py main.py benchmark` | Tournament between strategies |
| `py main.py pygame` / `pygame-ai` | Legacy desktop client (no doubling / Single Hand prompts) |

### Playing

* **Start New Game → Human vs AI**: you sit South (bottom) with an AI partner North (top).
  Type each player's name (including your own), pick each AI's personality, set the house rules, and deal.
* **AI vs AI**: watch four AIs with **every hand shown face up** to you, the spectator.
  The AIs themselves still only see their own cards. Use the bar at the top to pause,
  step one action or change speed.
* The ✦ button opens **AI Reasoning**: a short explanation of every AI decision.
  Switch on **Advanced** to see fuzzy inputs/outputs, fired rules, simulation
  counts and the candidate-move table.

---

## 2. Rules implemented

* 32 cards, 4 players, partners sit opposite (seats 1 & 3 vs 2 & 4). Dealing, bidding and play always go **clockwise**: you → left → top (partner) → right.
* Fair deal: a uniform shuffle from the operating system's random source, dealt one card at a time clockwise from the dealer's left.
* Rank in every suit: **J > 9 > A > 10 > K > Q > 8 > 7**. Points: J 3, 9 2, A 1, 10 1 (28 card points).
* Deal 4 cards → auction → trump → 4 more cards.
* **Duel auction**: the player after the dealer opens (16+); the next player clockwise must
  bid **higher** or pass, and the player holding the bid may **hold** at the same number.
  When one passes, the survivor duels the next player clockwise. Passing is final; the last
  player standing wins. Example: P1 16, P2 17, P1 holds 17, P2 18, P1 pass,
  P3 pass, P4 19, P2 holds 19, P4 20, P2 pass → P4 wins at 20.
* **Trump**: the winner chooses a secret suit or lets the concealed **7th card**
  decide. Trump is revealed when a player who cannot follow suit calls for it
  (with a cinematic reveal). Authentic abandonment rules: all 4 Jacks, all 8 cards
  of one suit, declarer without trump point cards, defenders with no trump.
* **Royal marriage** (K + Q of trump): ±4 to the declaring team's target (minimum 16).
* **Double / Redouble** (×2 / ×4): after the auction and the trump choice, while everyone still holds only 4 cards. The last four cards are dealt after the doubling is settled.
* **Scoring**: contract made +1 match point (× multiplier), failed −1; the match
  ends at ±target (default 6).

### Configurable house rules (set before each match)

| Rule | Options |
|---|---|
| Last-trick point | off (28) / on (29 points) |
| All four pass | dealer must play 16 / redeal |
| 7th-card trump | allowed / not allowed |
| Marriage | on/off · automatic on reveal **or** announced after the holder's team wins a trick · value 2–4 |
| Double & redouble | on / off |
| Match target | ±3, ±4, ±6, ±8 |

### Single Hand

Single Hand has several local interpretations, so **nothing is assumed** — every
part is a setting, and the AI's Single Hand decisions follow them:

| Setting | Options (default first) |
|---|---|
| When it can be called | after all 8 cards, before the first lead · as a special call during the auction |
| Partner | sits out (3-card tricks) · keeps playing |
| Partner's tricks count | no · yes (only if the partner plays) |
| Win condition | win all 8 tricks · and/or reach the normal contract target |
| Trump | no trump · declarer names trump openly |
| Scoring | win +3 / loss −3 (1–6 each) |

---

## 3. The AI

```
Card play:  masked GameState → legal moves → SO-ISMCTS (or exact Minimax in the endgame)
                                             → personality Fuzzy evaluator → chosen card
Bidding:    hand evaluation → personality Fuzzy bidding layer → Monte Carlo expected utility → Bid / Pass / Single Hand
```

**No cheating.** Agents only ever receive `GameState.get_masked_state_for_player()`:
their own cards and public information. Hidden cards are *sampled*, never read
(permuting the real hidden hands does not change the AI's decision).

| Module | Technique |
|---|---|
| `sim_engine.py` | Fast simulator; samples hidden deals consistent with played cards, hand sizes, inferred voids **and a belief over the unrevealed trump suit** |
| `mcts.py` | **Single-Observer ISMCTS**: a fresh determinization every iteration, one shared tree with availability counts, partnership-aware rollouts, personality utility for own-team nodes |
| `minimax.py` | **Alpha-beta Minimax** over several sampled deals once few cards remain; leaf value = point difference + contract result |
| `fuzzy_system.py` | Mamdani inference engine (min/max, centroid). Inputs: hand strength, trump strength, risk, current trick, capture chance, team position, opponent threat, card value |
| `mc_bidding.py` | Monte Carlo Expected-Utility Bidding with Common Random Numbers; reads partner/opponent bids |
| `ai_profiles.py` | The three personalities: thresholds, search budgets, utility weights and **separate fuzzy rule bases** |
| `ai_player.py` | Decision pipeline + explanations (full and "public" versions) |
| `knowledge_base.py`, `logic_engine.py` | Predicate facts (voids) and propositional move validation/proofs |

### How the personalities differ

| | Aggressive | Strategic | Defensive |
|---|---|---|---|
| Opening bar P(make) | 36 % | 45 % | 55 % |
| Outbidding an opponent | from 24 % | from 32 % | from 42 % |
| Opening | jumps up to +2 with a strong hand | minimum | minimum |
| Reads opponents' bids | barely | moderately | strongly |
| Overcalls partner | readily | with +2 headroom | rarely |
| Single Hand needs | 55 % | 78 % | 93 % |
| ISMCTS budget | 900 iterations | 1600 | 1200 |
| Utility | bonus for points taken *now* | contract result, plans ahead | penalties for wasting honours and feeding points |
| Fuzzy play rules | "capture valuable tricks" | "cheapest winner, save honours" | "play low under partner, deny points" |
| Calls for trump | eagerly | when worthwhile | only for big tricks |

`py main.py personalities` measures this. Typical output — identical opening
hands: Aggressive opens far more often than Strategic, and Defensive least; in play the
capture and high-card rates rank Aggressive > Strategic > Defensive, while
"play low when partner is winning" ranks Defensive > Strategic > Aggressive.

---

## 4. Project structure

```
main.py              launcher (gui, serve, headless, personalities, benchmark, pygame)
web_server.py        threaded local HTTP API + static files
game_controller.py   game flow: dealing, auction, trump, Single Hand, doubling, play, scoring
bidding.py           the clockwise multiple-call auction (one place for all bidding rules)
house_rules.py       configurable house rules incl. Single Hand
game_state.py rules.py card.py deck.py
ai_player.py ai_profiles.py mcts.py minimax.py sim_engine.py fuzzy_system.py mc_bidding.py
knowledge_base.py logic_engine.py evaluation.py
web/index.html web/style.css web/app.js   the browser table
web/cards/ web/assets/                    card and table artwork (SVG)
pygame_client/       legacy desktop client
```

## 5. Notes on the design

* **Stack**: the specification suggests FastAPI + React. This project keeps the
  zero-install Python standard library server and a vanilla-JS front end so it
  runs anywhere with just `py main.py`; the architecture (separate rules,
  bidding, AI, API and UI layers) is the same.
* **Seating**: your partner sits **opposite** (top), as at a real 29 table. A
  layout with the partner on the left cannot keep the alternating A-B-A-B turn
  order around the table.
* **Accessibility**: Settings include reduced motion (also honours the OS
  setting), animation pace, sound and volume.
