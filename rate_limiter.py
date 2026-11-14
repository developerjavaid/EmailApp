import threading
import time

# Azure Communication Services account-wide send quota for this resource:
# 100 emails/minute, 1000 emails/hour, shared across every clinic sending in
# a run (clinics send concurrently via ThreadPoolExecutor - see
# function_app._send_all_customer_emails). We pause a bit under those caps
# so a combined burst from several clinics never actually trips the real
# limit.
ACS_MINUTE_PAUSE_AT = 95
ACS_HOUR_PAUSE_AT = 990


class AcsRateLimiter:
    """Process-wide gate shared by every clinic's send loop in a single run.
    Call wait_for_slot() immediately before each send_email():
      - it blocks (sleeping across a minute boundary) while the account is
        at its per-minute cap, then keeps going;
      - it returns False once the per-hour cap is reached, so the caller can
        stop sending for this run instead of waiting out the hour in-process
        (which Azure's own execution-time limit wouldn't survive) - the next
        scheduled run (TIMER_SCHEDULE fires hourly) picks up the remainder.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._minute_key = None
        self._minute_count = 0
        self._hour_key = None
        self._hour_count = 0

    def wait_for_slot(self):
        while True:
            with self._lock:
                now = time.time()
                minute_key = int(now // 60)
                hour_key = int(now // 3600)

                if minute_key != self._minute_key:
                    self._minute_key = minute_key
                    self._minute_count = 0
                if hour_key != self._hour_key:
                    self._hour_key = hour_key
                    self._hour_count = 0

                if self._hour_count >= ACS_HOUR_PAUSE_AT:
                    return False

                if self._minute_count < ACS_MINUTE_PAUSE_AT:
                    self._minute_count += 1
                    self._hour_count += 1
                    return True

                sleep_for = 60 - (now % 60) + 0.5

            time.sleep(sleep_for)


rate_limiter = AcsRateLimiter()
