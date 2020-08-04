import collections
import time


class FPS:
    def __init__(self, window_len=50):
        self.frame_timestamps = collections.deque(maxlen=window_len)

    def count(self):
        self.frame_timestamps.append(time.time())

    def read(self):
        q_len = len(self.frame_timestamps)
        if q_len > 1:
            return q_len / (self.frame_timestamps[-1] - self.frame_timestamps[0])
        else:
            return 0.0
