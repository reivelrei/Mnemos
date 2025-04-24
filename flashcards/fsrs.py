import math
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional

from flashcards.models import ReviewState


# --- FSRS 4.5 Algorithm Implementation ---

class FSRS:
    """
    Implements the FSRS-4.5 algorithm logic.

    Reference implementation styles often seen in:
    - Anki FSRS Helper add-on
    - ts-fsrs library
    - Papers/documentation by Jarosz & Wozniak (Loci)
    """

    # Default FSRS-4.5 parameters (weights). Optimized parameters are better.
    # These defaults provide a reasonable starting point.
    DEFAULT_PARAMS = [
        0.4,  # w0: initial stability for rating 1 (Again)
        0.6,  # w1: initial stability for rating 2 (Hard)
        2.4,  # w2: initial stability for rating 3 (Good)
        5.8,  # w3: initial stability for rating 4 (Easy)
        4.93, # w4: difficulty multiplier for initial stability (used in R calc in some versions)
        0.94, # w5: stability multiplier for difficulty
        1.4,  # w6: difficulty change multiplier for Hard/Easy ratings
        # Parameter w7 below is often different or derived. Using a common value.
        0.02, # w7: difficulty change constant (affects how D changes)
        1.5,  # w8: exponential factor for stability increase
        0.1,  # w9: stability decay exponent for difficulty effect
        0.8,  # w10: factor for stability reset on lapse (Again)
        2.5,  # w11: exponent for difficulty in stability reset
        0.02, # w12: exponent for stability in stability reset
        0.2,  # w13: factor for retrievability effect on stability reset
        0.05, # w14: interval fuzz factor (not explicitly used in core calc below, but relevant for scheduling)
        0.33, # w15: factor for stability after lapse (Again) based on D
        1.50  # w16: exponent for difficulty after lapse (Again) based on D
        # Note: Some implementations might use slightly different parameter sets or interpretations.
    ]

    # Default desired retention rate
    DEFAULT_REQUEST_RETENTION = 0.9

    # Learning steps (in minutes) - Used when state is LEARNING or RELEARNING
    # For simplicity, we'll graduate directly to REVIEW state after the first correct answer
    # in LEARNING/RELEARNING based on calculated interval, but real Anki has fixed steps.
    # FSRS aims to replace fixed steps, so we calculate interval directly.

    def __init__(self, w: Optional[list] = None, request_retention: Optional[float] = None):
        self.w = w if w is not None else self.DEFAULT_PARAMS
        self.request_retention = request_retention if request_retention is not None else self.DEFAULT_REQUEST_RETENTION
        # Ensure we have enough parameters
        if len(self.w) < 17:
            raise ValueError(f"FSRS requires at least 17 parameters (weights). Found {len(self.w)}.")

    """
    def _map_rating(self, app_rating: int) -> int:
        
        Maps the application's specific rating scale (0, 3, 4, 5) to FSRS grade (1-4).
        ** Updated based on HTML button values **
        
        if app_rating == 0:
            return 1  # Again (Forgot)
        elif app_rating == 3:
            return 2  # Hard
        elif app_rating == 4:
            return 3  # Good
        elif app_rating == 5:
            return 4  # Easy
        else:
            # Handle unexpected values, maybe default to 'Good' or raise error
            print(f"Warning: Unexpected application rating received: {app_rating}. Defaulting to Good (3).")
            return 3  # Defaulting to Good might be safer than erroring out
            # Or: raise ValueError(f"Invalid application rating received: {app_rating}")
        """

    def update_state(
        self,
        current_state: str, # From ReviewState choices ('NEW', 'LRN', 'REV', 'REL')
        current_s: float,
        current_d: float,
        last_review_date: Optional[datetime],
        now: datetime,
        app_rating: int # Your app's rating (e.g., 0-5)
    ) -> Dict[str, object]:
        """
        Calculates the new state (S, D, state) and next interval based on a review.

        Args:
            current_state: The current state ('NEW', 'LRN', 'REV', 'REL').
            current_s: Current stability (S).
            current_d: Current difficulty (D).
            last_review_date: Timestamp of the last review (None if new).
            now: Timestamp of the current review.
            app_rating: User's performance rating from your app (e.g., 0-5).

        Returns:
            A dictionary containing:
            - new_s: New stability
            - new_d: New difficulty
            - new_state: New memory state
            - interval: Calculated interval in days for next review
        """

        # grade = self._map_rating(app_rating) # FSRS grade (1-4)
        grade = app_rating

        if current_state == ReviewState.NEW:
            # First review for this card
            new_s, new_d = self._calc_initial_sd(grade)
            new_state = ReviewState.LEARNING # Start in Learning state

            if grade == 1: # Again
                # Stay in learning, schedule soon (e.g., 1 minute? FSRS suggests interval=1)
                interval = 1 / (24 * 60) # Interval of 1 minute in days
            else: # Hard, Good, Easy
                 # Directly graduate to Review state after first success
                new_state = ReviewState.REVIEW
                # Calculate interval based on initial stability
                interval = self._calc_interval(new_s)

        elif current_state in [ReviewState.LEARNING, ReviewState.RELEARNING]:
            if last_review_date is None:
                 # Should not happen for LRN/REL states, but handle defensively
                return self.update_state(ReviewState.NEW, 0.0, self.w[4], None, now, app_rating)

            elapsed_days = max(0, (now - last_review_date).total_seconds() / (24 * 60 * 60))
            new_d = self._calc_new_difficulty(current_d, grade) # Update difficulty first
            new_d = max(1.0, min(10.0, new_d)) # Clamp D

            if grade == 1: # Again
                # Failed while in learning/relearning -> Reset stability, stay/enter RELEARNING
                new_s = self._calc_stability_after_lapse(current_s, new_d)
                new_state = ReviewState.RELEARNING
                # Short interval for relearning (e.g., 10 minutes? FSRS suggests 10)
                interval = 10 / (24 * 60) # Interval of 10 minutes in days

            else: # Hard, Good, Easy
                # Succeeded while in learning/relearning -> Graduate to REVIEW
                retrievability = self._calc_retrievability(current_s, elapsed_days)
                new_s = self._calc_stability_after_success(current_s, new_d, retrievability, grade)
                new_state = ReviewState.REVIEW
                interval = self._calc_interval(new_s)

        elif current_state == ReviewState.REVIEW:
            if last_review_date is None:
                 # Should not happen for REV state, but handle defensively
                 return self.update_state(ReviewState.NEW, 0.0, self.w[4], None, now, app_rating)

            elapsed_days = max(0, (now - last_review_date).total_seconds() / (24 * 60 * 60))
            retrievability = self._calc_retrievability(current_s, elapsed_days)
            new_d = self._calc_new_difficulty(current_d, grade) # Update difficulty first
            new_d = max(1.0, min(10.0, new_d)) # Clamp D

            if grade == 1: # Again (Lapse)
                # Failed a review card -> Reset stability, enter RELEARNING
                new_s = self._calc_stability_after_lapse(current_s, new_d) # Pass new_d
                new_state = ReviewState.RELEARNING
                # Short interval for relearning (e.g., 10 minutes?)
                interval = 10 / (24 * 60) # 10 minutes in days

            else: # Hard, Good, Easy
                # Succeeded on a review card -> Update stability, stay in REVIEW
                new_s = self._calc_stability_after_success(current_s, new_d, retrievability, grade) # Pass new_d
                new_state = ReviewState.REVIEW
                interval = self._calc_interval(new_s)

        else:
            raise ValueError(f"Unknown current state: {current_state}")

        # Ensure stability is positive
        new_s = max(0.1, new_s) # Minimum stability of 0.1 days

        # Round interval to nearest whole day, minimum 1 day (unless it's a short learning interval)
        if interval >= 1:
            interval = max(1, round(interval))
        # else: keep short intervals precise (e.g., for minutes)


        return {
            "new_s": new_s,
            "new_d": new_d,
            "new_state": new_state,
            "interval": interval, # In days
        }

    def _calc_initial_sd(self, grade: int) -> Tuple[float, float]:
        """Calculates initial S and D based on the first grade."""
        # Initial stability (S) comes directly from parameters w0-w3 based on grade
        initial_s = self.w[grade - 1]
        # Initial difficulty (D) is influenced by the first grade relative to "Good" (grade 3)
        initial_d = self.w[4] - self.w[5] * (grade - 3)
        # Clamp initial D
        initial_d = max(1.0, min(10.0, initial_d))
        return initial_s, initial_d

    def _calc_retrievability(self, stability: float, elapsed_days: float) -> float:
        """Approximation of retrievability (R)."""
        if stability <= 0: return 0.0 # Avoid division by zero or math domain errors
        # Using the common approximation R = (1 + t / (9 * S)) ** -1
        # FSRS parameter w4 is sometimes involved here too, depending on version.
        # R = self.w[4] ** (elapsed_days / stability) is another form. Using simpler one for now.
        return (1 + elapsed_days / (9 * stability)) ** -1

    def _calc_new_difficulty(self, current_d: float, grade: int) -> float:
        """Calculates the new difficulty (D')."""
        # D' = D - w6 * (g - 3) -> more difficult for 'Hard' (g=2), easier for 'Easy' (g=4)
        # Another form: D' = w5*D + (1-w5) * (w7 * (11-D) * math.exp(1-R)) - w6 * (g-3)
        # Using simpler form:
        new_d = current_d - self.w[6] * (grade - 3)
        # Optional: Apply mean reversion using w7 (makes D trend towards a middle value over time)
        # new_d = new_d + self.w[7] * (self.w[4] - new_d) # Reverts towards w[4]
        return new_d # Clamping happens in the main update method

    def _calc_stability_after_success(self, current_s: float, current_d: float, retrievability: float, grade: int) -> float:
        """Calculates new stability (S') after a successful review (grade > 1)."""
        # Base stability increase factor
        hard_penalty = 1.0 if grade == 2 else 0.0 # Grade 'Hard' penalty
        easy_bonus = 1.0 if grade == 4 else 0.0   # Grade 'Easy' bonus

        # Core stability update formula (common FSRS-4.5 style)
        # S' = S * (1 + exp(w8) * (11 - D) * S^(-w9) * (exp(1 - R) - 1))
        factor = math.exp(self.w[8]) * (11 - current_d) * (max(0.1, current_s) ** -self.w[9]) # Ensure S isn't zero
        stability_increase = max(0, factor * (math.exp(1 - retrievability) - 1))

        # Optional: Modify increase based on grade (Hard/Easy) - Simpler approach
        # More complex models might incorporate grade directly into the exp factors
        # This is a simpler scaling approach.
        # Let's use the base increase for Good, slightly less for Hard, slightly more for Easy
        # Not directly using w[1] to w[3] here, as they are initial values.
        # Simpler: Assume the core formula accounts for difficulty, grade adjusts it slightly if needed.
        # Let's stick to the core formula for now as it's standard for g > 1.

        # S' = S * (1 + stability_increase)
        # An alternative stability increase formula based on grade: S' = S * (1 + factor) * grade_factor[g]
        # Let's use the standard:
        new_s = current_s * (1 + stability_increase)

        # Apply modification for 'Hard' penalty or 'Easy' bonus (if desired, many versions don't explicitly do this)
        # Example (adjust multipliers as needed):
        # if hard_penalty: new_s *= 0.8 # Reduce computed stability if 'Hard'
        # if easy_bonus: new_s *= 1.2  # Increase computed stability if 'Easy'

        return new_s

    def _calc_stability_after_lapse(self, current_s: float, current_d: float) -> float:
        """Calculates new stability (S') after a lapse (grade = 1)."""
        # S' = w10 * D^(-w11) * S^(w12) * exp(1 - R) -> More complex form
        # Simplified/common reset form: S' = w15 * D^(-w16)
        new_s = self.w[15] * max(1.0, current_d) ** (-self.w[16])
        return new_s

    def _calc_interval(self, stability: float) -> float:
        """Calculates the next interval in days based on stability and desired retention."""
        if stability <= 0: return 1 # Minimum interval 1 day if stability is non-positive

        # Solve R = (1 + I / (9 * S))^-1 for I when R = request_retention
        # I = 9 * S * (R^-1 - 1)
        # I = 9 * S * ((1/request_retention) - 1)
        interval = 9 * stability * ( (1 / self.request_retention) - 1 )

        # Add fuzz? (Optional, adds randomness to intervals)
        # interval *= (1 + random.uniform(-self.w[14], self.w[14]))

        return max(1, interval) # Ensure interval is at least 1 day
