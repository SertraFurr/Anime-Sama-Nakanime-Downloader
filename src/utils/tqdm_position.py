import threading

# Assigns each concurrent tqdm bar (downloads, conversions, ...) its own
# terminal line instead of letting them all draw over line 0 - without this,
# several bars running in parallel (batch threaded mode) produce a garbled,
# overlapping display. Shared across download and conversion so the two
# phases don't fight over the same rows.
_lock = threading.Lock()
_in_use = set()


class TqdmPosition:
    def __enter__(self):
        with _lock:
            pos = 0
            while pos in _in_use:
                pos += 1
            _in_use.add(pos)
            self.pos = pos
        return self.pos

    def __exit__(self, exc_type, exc_val, exc_tb):
        with _lock:
            _in_use.discard(self.pos)
