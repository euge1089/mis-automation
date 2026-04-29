"""
Adaptive price/rent band sizing for MLS searches.

Uses result-count feedback to widen ranges in thin markets and shrink in dense
segments — no model training, just heuristics (online "learning" in the control sense).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# MLS results grid / export typically caps at this many rows; bands above it lose listings.
HARD_MAX_LISTING_RESULTS = 1000


@dataclass
class AdaptiveRangeState:
    """Mutable probe size carried across chunks for one scraper run."""

    step: int
    min_step: int
    max_step: int
    max_results_safe: int = 950

    def after_success(self, count: int) -> None:
        """Tune next default step after a downloadable band (aggressive adapt)."""
        if count <= 0:
            return
        cap = self.max_results_safe
        # Dense — narrow next probe sooner and harder
        if count >= int(cap * 0.88):
            self.step = max(self.min_step, int(self.step * 0.42))
        elif count >= int(cap * 0.65):
            self.step = max(self.min_step, int(self.step * 0.72))
        elif count >= int(cap * 0.45):
            self.step = max(self.min_step, int(self.step * 0.88))
        # Thin — widen faster on the next chunk
        elif count < 45:
            self.step = min(self.max_step, int(max(self.step, self.step * 2.4)))
        elif count < 110:
            self.step = min(self.max_step, int(max(self.step, self.step * 1.85)))
        elif count < 260:
            self.step = min(self.max_step, int(max(self.step, self.step * 1.38)))
        elif count < 420:
            self.step = min(self.max_step, int(max(self.step, self.step * 1.15)))

    def after_zero_results(self) -> None:
        """No listings in band — next segment may be sparse; allow a wider probe."""
        self.step = min(
            self.max_step,
            max(self.step * 2, self.min_step * 3),
        )


def _widen_band_toward_cap(
    start: int,
    end: int,
    count: int,
    max_bound: int,
    cap: int,
    count_for_range: Callable[[int, int], int],
    *,
    label: str,
    max_queries: int = 22,
    min_high_over_cap: int | None = None,
) -> tuple[int, int]:
    """
    After a valid [start, end] with 0 < count <= cap, push end upward as far as possible
    while keeping count <= cap (monotone in price). Fills each download chunk toward the cap.

    min_high_over_cap: smallest high-end price probed during shrink that was still over the
    cap. Then any high >= that value is still over the cap, so widening only needs to search
    up to min_high_over_cap - 1 (not max_bound). Avoids useless probes like 700–10612 when
    we already know 700–1700 was over the cap.

    cap is kept below the MLS hard limit (e.g. 950 vs ~1000).
    """
    if end >= max_bound or count <= 0:
        return end, count
    if count > cap:
        return end, count

    # Upper bound for binary search: cannot exceed a high we already know is over cap.
    hi_limit = max_bound
    if min_high_over_cap is not None:
        hi_limit = min(hi_limit, min_high_over_cap - 1)
    if hi_limit <= end:
        return end, count

    # Widen only via binary search on [end, hi_limit]. Avoid an initial
    # count_for_range(start, max_bound) probe: it jumps the UI to the global
    # cap (e.g. rent $20k) which is confusing, slow, and risks a stale Results
    # label if the count text lags after the last shrink step.
    queries = 0
    lo, hi = end, hi_limit
    best_end, best_count = end, count
    while lo < hi and queries < max_queries:
        mid = (lo + hi + 1) // 2
        queries += 1
        cm = count_for_range(start, mid)
        if cm <= cap:
            lo = mid
            best_end, best_count = mid, cm
        else:
            hi = mid - 1

    if best_end > end:
        print(
            f"  {label}: widened end ${end:,} → ${best_end:,} "
            f"({count} → {best_count} results, max allowed {cap})"
        )
    return best_end, best_count


def shrink_end_until_download_safe(
    start: int,
    end: int,
    prev_count: int,
    count_for_range: Callable[[int, int], int],
    *,
    label: str,
    hard_max: int = HARD_MAX_LISTING_RESULTS,
    max_queries: int = 40,
) -> tuple[int, int]:
    """
    Re-read listing count for [start, end] and, if it exceeds ``hard_max`` (stale UI during
    widen, or a $1 step crossing the MLS cap), binary-search the largest end in [start, end]
    such that the count fits the grid/export limit.

    Adaptive probing still uses max_results_safe (e.g. 950); this step only enforces the
    hard MLS ceiling so we do not download a "1020 results" band that truncates at 1000 rows.

    Heuristics:
    - Any fresh count in [990, hard_max] is accepted as-is (good enough fill).
    - If we cannot find a fresh band <= hard_max, we fall back to the last under-cap
      estimate from the adaptive layer (prev_count) rather than throwing.
    """
    c = count_for_range(start, end)
    if c <= hard_max:
        if c >= hard_max - 10:
            # 990–1000 results: accept without further narrowing.
            return end, c
        return end, c

    print(
        f"  {label}: fresh count {c:,} exceeds MLS grid limit ({hard_max:,}); "
        f"narrowing upper price to capture all rows…"
    )
    lo, hi = start, end
    best_end: int | None = None
    best_count: int | None = None
    queries = 0
    while lo <= hi and queries < max_queries:
        queries += 1
        mid = (lo + hi + 1) // 2
        cm = count_for_range(start, mid)
        if cm <= hard_max:
            # Track the best fresh band under the hard limit, preferring counts closer
            # to the top of the grid (>=990 if possible).
            if best_end is None:
                best_end, best_count = mid, cm
            else:
                assert best_count is not None
                # Prefer higher counts, with a soft target of >=990.
                if (cm >= 990 and best_count < 990) or (cm > best_count and cm <= hard_max):
                    best_end, best_count = mid, cm
            lo = mid + 1
        else:
            hi = mid - 1

    if best_end is not None and best_count is not None:
        if best_end != end:
            print(
                f"  {label}: narrowed end ${end:,} → ${best_end:,} "
                f"({c:,} → {best_count:,} results, cap {hard_max:,})"
            )
        return best_end, best_count

    # No stable fresh band under the hard cap — fall back to the last under-cap estimate
    # from the adaptive layer (prev_count) instead of aborting the whole run.
    print(
        f"  {label}: could not find a fresh band under {hard_max:,} results; "
        f"falling back to previous estimate ({prev_count:,} results up to ${end:,})."
    )
    return end, prev_count


def find_valid_span(
    start: int,
    max_bound: int,
    state: AdaptiveRangeState,
    count_for_range: Callable[[int, int], int],
    *,
    label: str = "range",
    max_shrink_iters: int = 60,
    widen_valid_band: bool = True,
) -> tuple[int, int]:
    """
    Find end such that [start, end] has count in (0, max_results_safe], or count==0.

    If widen_valid_band is True (default), after a sub-cap count the end price is pushed up
    via binary search toward the cap. Widen never searches above a high already known to
    be over the cap during shrink (e.g. will not try $10k+ when $1,700 already failed).

    If False, the first sub-cap band is accepted as-is (no widen).

    count_for_range(low, high) must run the UI query and return the MLS result count.
    Returns (end, count).
    """
    if start > max_bound:
        raise ValueError(f"start {start} > max_bound {max_bound}")

    cap = state.max_results_safe
    span = max_bound - start
    step = max(state.min_step, min(state.step, span))
    if step <= 0:
        step = state.min_step

    min_high_over_cap: int | None = None

    for _ in range(max_shrink_iters):
        end = min(start + step, max_bound)

        print(f"Checking {label} ${start:,} to ${end:,} (probe step ${step:,})...")
        count = count_for_range(start, end)
        print(f"  -> {count} results")

        if count == 0:
            state.after_zero_results()
            print(f"  Next default probe: ${state.step:,} (wider after 0 results)")
            return end, 0

        if count <= cap:
            if widen_valid_band:
                end, count = _widen_band_toward_cap(
                    start,
                    end,
                    count,
                    max_bound,
                    cap,
                    count_for_range,
                    label=label,
                    min_high_over_cap=min_high_over_cap,
                )
            end, count = shrink_end_until_download_safe(
                start,
                end,
                count,
                count_for_range,
                label=label,
            )
            state.after_success(count)
            print(f"  Next default probe: ${state.step:,} (tuned from {count} results)")
            return end, count

        # Too many results: shrink harder (tighter target ratio + steeper fallback)
        min_high_over_cap = (
            end if min_high_over_cap is None else min(min_high_over_cap, end)
        )
        target = max(state.min_step, int(step * cap * 0.88 / max(count, 1)))
        if target >= step:
            target = max(state.min_step, step // 3)
        elif target > step * 0.92:
            target = max(state.min_step, int(step * 0.55))
        step = target
        print(f"  Shrinking same-start probe to ${step:,} (was over {cap} results)")

    raise ValueError(
        f"Could not find a valid {label} under {cap} results starting at ${start:,}"
    )
