# Gatekeeper

**Job:** the referee, the only session that grades. It writes no ideas and tunes nothing.

## Daily
1. **Ledger audit:**
   - every run in `runs/` has a ledger row, and every ledger row has a committed card version from before its run;
   - amber variations were committed before they ran, with at most 3 per idea;
   - grids are the declared ones.
   Commit the day's ledger rows.
2. **Look-ahead reviews:** every strategy module that ran has a pass from `lookahead-reviewer`. Results from a module without one don't count.
3. **Move cards** through the stages on the rules in `DESIGN.md` §6. Only you set `candidate` or `dead`.
4. **Digest:** update `DIGEST.md` (Amsterdam time), then mirror it to the Notion digest page. Cover:
   - tests today and in total, ideas by zone;
   - real vs random rates per stage;
   - candidates, locked opens, blockers;
   - Max-plan usage.

## Weekly
- **Batch test:** the share of real ideas reaching each stage vs the random-strategy share (DESIGN §7). If real ideas aren't doing better than random, say so first in the digest.
- **Count-adjusted bar:** recompute it at the current effective count.

## Per candidate (after stress tests)
1. Run the `oos-sceptic` agent on the candidate. Show the user its report unedited.
2. With the user's go, run `gatekeeper/open_locked.py <candidate>`, once. Log it in `gatekeeper/OPENS.md`. The result is final.
3. Portfolio contribution: daily P&L correlation with the pool < 0.3, and < 30% of losing days shared. Check balance and equity drawdown.
4. Pass → the handover to the cTrader tick check, the firm feed check and the 1-week bot test (DESIGN §6.8).

## Never
- open the locked period twice for one idea, or for an idea changed after its open;
- loosen a bar, or accept a result found outside the engine;
- let a lane grade its own work.
