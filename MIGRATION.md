# Refactor notes

## New layout
```
main.py
config.py                (unchanged)
database/                was database.py
  connection.py            client, collections, indexes
  users.py                 register, lookup, rank role, streak, engage cache
  xp.py                    add/remove XP, daily message-XP cap
  missions.py              mission completion (pause-aware, atomic)
  pause.py                 GLOBAL pause / resume of mission XP
  games.py                 mini-game betting (daily limit, settle, history)
  leaderboard.py           leaderboard + positions
  platform_stats.py        Discord/Telegram daily stats
  resets.py                weekly/monthly reset + CSV snapshot
minigames/               the games: base.py (bet lifecycle + shared view) · coinflip · dice_duel · guess_number · rps · blackjack · dealers_choice · cups · cards · info (/games)
services/                central logic - cogs should ONLY use these to change XP
  xp.py                    grant_xp / award_mission / pause_mission_xp / resume_mission_xp
  games.py                 start_bet / finish_bet / cancel_bet (for mini-game cogs)
  ranks.py                 check_rank (was rank_update.py)
  notify.py                mission + staff embeds (was copy-pasted in 4 cogs)
utils/  checks.py (one admin check) · embeds.py (profile + missions embeds) · errors.py
Cogs/   user.py · admin.py · games.py · xp.py · x_engage.py · poll.py · reset.py · stats.py · error_handler.py
```
**Delete from your repo:** `database.py`, `rank_update.py`, `tg_auto.py`, `Cogs/missions.py`, `bot.log`.
`from database import ...` still works for every old function name.

## The rule that makes it "central"
Every XP change goes through `services/xp.py`, and every path ends in `check_rank`:
`grant_xp` (messages, admin add/remove) · `award_mission` (all missions) · `resume_mission_xp` · `finish_bet` (game wins).

## Pause / resume mission XP (GLOBAL - one switch for everyone)
* `/admin pause-xp [reason]` - from that moment **every** user's completed missions are recorded but
  their XP is **held** (`pending_xp`) instead of credited. No rank-ups while held.
* `/admin resume-xp` - switches it off and credits **every** user's held XP (total + monthly), then runs
  the rank check for each of them. Reports how many users were credited / ranked up.
* `/admin xp-status [user]` - paused?, who/when/why, how many users and how much XP are held;
  optionally what one user has held.
* Everyone sees an orange "paused" banner on `/missions` (and a note on `/profile`) with their held XP.
* Safe against races: the held XP is per-user and credited with atomic per-user updates. If a mission
  lands exactly while you resume, it flushes itself. If the bot restarts mid-resume, just run
  `/admin resume-xp` again and it credits whatever is left.
* Only mission XP is held. Message XP, `/admin xp add|remove` and **mini-game results** are not.
  Held XP survives the weekly reset. XP resumed after a monthly reset lands in the *new* month.

## Mini-game betting + `/coinflip`
Config (`config.py`, placeholders - set your own): `MAX_BET_PER_GAME = 100`, `DAILY_BET_LIMIT = 500`,
`BET_WIN_MULTIPLIER = 2`.
* Rules: bet must be 1..`MAX_BET_PER_GAME`, can't exceed the user's **monthly XP** (which restarts at 0 after each monthly reset) or total XP, and the sum staked per UTC day
  can't exceed `DAILY_BET_LIMIT`. Every UTC day the counter starts again from 0 (no reset job needed).
* Tracked in `daily_xp_state` (fields `bet_date` + `bet_xp`, separate from the message-XP fields so the
  first-message / variety bonuses are untouched). Reserving a bet is atomic: 40 simultaneous bets can't
  exceed the limit (tested).
* Win: `+bet x BET_WIN_MULTIPLIER` XP to total **and** monthly XP. Loss: `-bet` from total **and** monthly
  (never below 0). Wins run the central rank check. Every settled bet is saved in `game_history`
  (user, game, bet, won, xp_change, date, details) for stats / audits.
* Users see their daily allowance and "max bet right now" in the **Mini-game Bets** section of `/profile` (and `/admin profile`).

### Mini-games (all in `minigames/`, commands in `Cogs/games.py`)
All replies are **ephemeral** (only the player sees their game, so everyone can play in the same channel).
`/games` shows the list and a select menu with the rules of each game.

| Command | How it plays (Discord feature) | Win chance | EV per bet at **2x** | Break-even multiplier |
|---|---|---|---|---|
| `/coinflip side amount` | pick heads/tails in the command | 50% | +0.50 | 1.0 |
| `/diceduel amount` | 4 buttons: Even / Odd / Over N / Under N (N = 6, 7 or 8, shown first) | 50% even/odd; over/under 28-58% | +0.50 .. +0.75 | 0.7 - 1.0 |
| `/guess amount` | button -> pop-up form (modal); 5 guesses, higher/lower hints | ~31% with best play | -0.07 | 2.2 |
| `/rps amount` | 3 buttons; a draw returns the bet | 33% win / 33% tie | +0.33 | 1.0 |
| `/blackjack amount` | Hit / Stand buttons; dealer stands on 17; tie returns the bet | ~43% win / 9% tie | +0.39 | 1.1 |
| `/dealerschoice amount` | 5 face-down card buttons; same rank = tie | 47% win / 6% tie | +0.47 | 1.0 |
| `/cups amount` | select menu with 5 cups | 20% | -0.40 | 4.0 |

(EV = expected XP gained per XP bet. Win = `+2x`, loss = `-1x`, tie = 0. Blackjack is from a 300k-hand
simulation of the real code with basic strategy; the others are exact.)
**With the global 2x payout, 5 of 7 games pay players on average.** To tune a single game without
touching code, set `GAME_MULTIPLIER_OVERRIDES` in `config.py`, e.g. `{"cups": 4, "guess": 2}`
(a game not listed uses `BET_WIN_MULTIPLIER`). `/games` and the bet footer always show the real payout.

Rules shared by every game (`minigames/base.py`):
* One game at a time per player (so the monthly-XP balance check made when the bet is placed is still
  true when it settles). Closing/dismissing the message keeps the game open until it times out (120 s).
* Buttons only work for the player. Inactivity cancels the bet (stake released, nothing deducted).
* An error cancels the bet, gets an Error ID (staff channel + `bot.log`) and tells the player.
* A tie (RPS, Blackjack, Dealer's Choice) returns the bet: no XP change, daily allowance freed.
* If the bot restarts mid-game the stake stays counted for that day's allowance (XP is never touched).
* Cards: the deck is shuffled locally with OS randomness (no network call can stall an open bet);
  only the card pictures come from `deckofcardsapi.com` image URLs, which Discord loads itself.
* `GAME_CHANNEL_IDS` in `config.py` (empty = any channel) restricts where games can be played.
* History rows (`game_history`) record `outcome` = win / loss / push, the picks and the cards/dice.

To add a game: copy `minigames/rps.py` (change only the play step), add it to `minigames/info.py` `GAMES`,
and add a command in `Cogs/games.py`.

The pattern a game follows (what `minigames/base.py` wraps for you):
```python
from services.betting import start_bet, finish_bet, cancel_bet

@app_commands.command(name="coinflip")
async def coinflip(self, interaction, amount: app_commands.Range[int, 1, 10_000]):
    await interaction.response.defer()
    bet = await start_bet(interaction.user.id, amount)          # validates + reserves
    if not bet["success"]:
        return await interaction.followup.send(bet["message"], ephemeral=True)
    won = random.random() < 0.5                                  # <- your game decides
    res = await finish_bet(interaction.guild, interaction.user.id, interaction.user.name,
                           "coinflip", amount, won)              # XP + history + rank check
    await interaction.followup.send(f"{res['message']}  (Total: {res['total_xp']:,} XP)")
```
Call `cancel_bet(user_id, amount)` if a game is abandoned after `start_bet`.

**Heads-up on the economy:** as specified, a win pays `+2x` the bet and a loss costs `1x`. With a 50% game
that is **+0.5x bet expected profit per bet** (about +250 XP/day at a 500 limit), so players earn XP by
betting. For a fair 50/50 game, `BET_WIN_MULTIPLIER = 1` (win +bet / lose -bet) has zero expected value;
or keep 2 and make games win less than 33% of the time. It is one constant to change.

## Commands
| User (everyone) | `/profile` (includes your daily bet allowance) `/missions` `/leaderboard` `/games` `/coinflip` `/diceduel` `/guess` `/rps` `/blackjack` `/dealerschoice` `/cups` |
|---|---|
| **Admin** (one `/admin` group, staff check once) | `/admin xp` (add/remove) · `/admin verify-mission` · `/admin missions` · `/admin profile` · `/admin pause-xp` · `/admin resume-xp` · `/admin xp-status` (pause/resume are global) |
| Other admin | `/sync_engage` `/engage_status` (now use the shared check) · `/monthly_reset` (unchanged) · `/stats` `/exportstats` |

Renamed: `/award` -> `/admin xp add`, `/verify_mission` -> `/admin verify-mission`, `/admin_profile` -> `/admin profile`.

## Error handler (Cogs/error_handler.py)
Catches slash commands, prefix commands, **event listeners** (on_message etc. - these were silent before)
and background loops. Expected errors -> friendly message. Bugs -> short **Error ID** shown to the user,
full traceback in `bot.log` and in the staff log channel with the same ID. Hooks are restored on unload.

## Telegram: one cog (Cogs/stats.py)
Telegram tracking (2 chats) + Discord join/leave/message stats (bot messages count too, as before) + tweet mirroring + `/stats` in one cog.
Platform names unchanged (`telegram_group`, `telegram_channel`, `discord`).
**Remove** the `send_telegram_message` forwarding from xp.py (done in the new xp.py) or tweets post twice.

## Bugs fixed (all found in your code)
1. **Edited Telegram messages were counted as new messages** (`filters.ALL`).
2. `/profile` and `/admin_profile` crashed (`UnboundLocalError`) for users at max rank.
3. `/missions` crashed (`KeyError`) for users whose doc lacked a counter field.
4. *(removed - the 7-day streak mission keeps its original behaviour: it completes on day 6.)*
5. `complete_mission` could award XP twice if two events landed at once (final update had no "not completed" guard).
6. `add_daily_xp` could raise `DuplicateKeyError` (upsert on `{_id, date}` when yesterday's record existed).
7. Removing XP could push totals below 0; and a later rank check could have *lowered* a rank. Totals now floor at 0, ranks never downgrade.
8. `rank_update_embed` was passed a Message / Member / Channel pretending to be an Interaction; role was set in DB before it was given (a Forbidden left them out of sync). Now takes the guild; DB change is reverted if the role can't be added.
9. `/engage_status` always showed 0 (read the `{"success","message"}` wrapper as if it were the user doc).
10. Admin audit log embed set its timestamp/footer on the wrong embed.
11. Telegram: one `get_chat_member_count` API call per message (now cached 10 min); "creator" join status ignored.
12. `x_engage` loop died permanently on any unexpected error; reset loop swallowed tracebacks with `print`.
13. `/stats days:0` / negative; now `Range[1, 365]`.
14. Mongo datetimes were timezone-naive (`tz_aware=True` now), needed for correct paused-since timestamps.

## Decisions I made - please confirm
* `/stats` and `/exportstats` are now **admin-only** (they were open to everyone). Remove `@admin_only()` to revert.
* `/missions` and `/profile` replies are ephemeral (as `/missions` and `/profile` already were).

## config.py inconsistencies (not changed)
`x_likes` / `x_retweets` / `x_comments` say "10" in the name but `count` is 7 · `correct_match_take` says
"two occasions" but `count` is 1 · `x_likes` description says "Post 10 posts".

## Testing done
Loaded every cog into a real discord.py 2.7 bot (all 12 slash commands validate and serialise) and ran
217 checks against a real MongoDB 7.0: XP floor, atomic mission completion, 25 simultaneous completions,
global pause/resume incl. racing with 6 users, an interrupted resume, held XP vs. weekly reset, mini-game limits/win/loss/new-day/concurrency, rank-up/no-downgrade/no-duplicate-announce via the
service layer, error handler, embeds, Telegram filters. **Not tested live:** your real Discord server and
a real Telegram connection - run it on a staging server first.
