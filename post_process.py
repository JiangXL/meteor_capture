import time
import cv2 as cv
import numpy as np
from collections import deque
import datetime
from multiprocessing import Queue, Process
from queue import Full
from threading import Thread


class ImageBuffer:
    def __init__(self, maxlen=60):
        self._images = deque(maxlen=maxlen)
        self.maxlen = maxlen

    def add(self, img, t=None):
        if t is None:
            t = datetime.datetime.utcnow()
        self._images.append({'img': img, 'time': t})

    def getLast(self):
        return self._images[-1]

    # return a copy
    def getCopy(self):
        return self._images.copy()


def scale_rect(rect, k):
    x, y, w, h = rect

    x = max(0, x + (1-k) * w / 2)
    y = max(0, y + (1-k) * h / 2)

    w = max(w*k, 40)
    h = max(h*k, 40)
    return int(x), int(y), int(w), int(h)


def contour_centroid(cnt):
    M = cv.moments(cnt)
    cx = int(M['m10']/M['m00'])
    cy = int(M['m01']/M['m00'])
    return cx, cy


class GlobalEvent:
    def __init__(self, cnt, area):
        self.center = contour_centroid(cnt)
        self.max_rect = cv.boundingRect(cnt)
        self.max_area = area
        self.st_t = time.time()
        self.updated = self.st_t
        # record start/end position to filter out stationary blinks
        self.st_pos = np.array([self.max_rect[0], self.max_rect[1]])
        self.last_pos = self.st_pos

    def isInPrevContour(self, cnt) -> bool:
        pt = self.center
        rect = cnt.max_rect
        return rect[0] - 5 < pt[0] < rect[0] + rect[2] + 5 and rect[1] - 5 < pt[1] < rect[1] + rect[3] + 5

    def update(self, area, rect):
        self.updated = time.time()
        self.last_pos = np.array([rect[0], rect[1]])
        if area > self.max_area:
            self.max_area = area
            self.max_rect = rect


class Processor:
    def __init__(self, conf, dark=None):
        self._buffer = ImageBuffer()
        self._dark = dark
        self._threshold = 50
        self.global_events = {}
        self._fps = 1 / float(conf['capture']['exposure'])
        self._runningAvg = np.zeros((int(conf['capture']['size_h']), int(conf['capture']['size_w'])), dtype=np.float32)
        self._replay = None
        self.streamer = None
        self._prev = None

        self.frame_queue = Queue(maxsize=30)

    def process(self, img: np.array):
        if self._dark:
            img -= cv.absdiff(img, self._dark)
        self._buffer.add(img)

        #cur = np.float32(img)
        cur = img
        #cur = cv.cvtColor(img, cv.COLOR_BAYER_RG2GRAY)
        if self._prev is not None:
            prev = self._prev
        else:
            prev = cur

        # smooth
        cur = cv.medianBlur(cur, 3)

        diff = cv.absdiff(cur, prev)
        _, diff_bin = cv.threshold(diff, 20, 255, cv.THRESH_BINARY)
        self._prev = cur
        #cv.accumulateWeighted(diff_bin, self._runningAvg, 0.2)
        #avg_img_int = cv.convertScaleAbs(self._runningAvg)
        avg_img_int = diff_bin
        #_, contours, hierarchy = cv.findContours(avg_img_int, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        contours, hierarchy = cv.findContours(avg_img_int, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)

        for c in contours:
            contour_area = cv.contourArea(c)
            #if contour_area > 20:
            if contour_area > 3:
                contour = GlobalEvent(c, contour_area)
                centroid_str = str(contour.center)
                if centroid_str in self.global_events:
                    self.global_events[centroid_str].update(contour_area, contour.max_rect)
                else:
                    new = True
                    for k, v in self.global_events.items():
                        if contour.isInPrevContour(v):
                            new = False
                            v.update(contour_area, contour.max_rect)
                            break
                    if new:
                        self.global_events[centroid_str] = contour

        to_discard = []
        now = time.time()
        replay = False
        for ge_k in self.global_events:
            ge: GlobalEvent = self.global_events[ge_k]
            last_updated = ge.updated
            # trail ended
            if now - last_updated > 0.1:
                to_discard.append(ge_k)

                # exclude trails that are too short or too long
                if 0.3 < last_updated - ge.st_t < 20:
                    # exclude stationary trails
                    if np.linalg.norm(ge.st_pos - ge.last_pos) > 5:
                        #self.replay(self._buffer.getCopy(), ge.max_rect)
                        self.saveMeteor(self._buffer.getCopy())
                        replay = False
                        break

        for k in to_discard:
            del self.global_events[k]

        # do not send if replay is in action
        if not replay and self.frame_queue.qsize() < 20:
            img = cv.cvtColor(img, cv.COLOR_BAYER_BG2BGR)
            self.toLive(img)

    def saveMeteor(self, buf):
        def saveMeteor(buffer):
            size = buffer[0]['img'].shape
            #fourcc = cv.VideoWriter_fourcc('H', '2', '6', '4')
            fourcc = cv.VideoWriter_fourcc('X', 'V', 'I', 'D')
            vw = cv.VideoWriter(f"{buffer[0]['time'].strftime('%Y-%m-%d-%H_%M_%S.%f')[:-3]}.mkv", fourcc,
                                self._fps, size[::-1])

            for i, obj in enumerate(buffer):
                img = obj['img']
                img = cv.cvtColor(img, cv.COLOR_BAYER_BG2BGR)
                vw.write(img)
            vw.release()
            print("--------------saving DONE--------------")
        print("--------------saving--------------")
        pro = Process(target=saveMeteor, args=(buf,))
        pro.daemon = True
        pro.start()

    def replay(self, buffer, roi_rect):
        # discard frames during cool down time
        max_ctr = buffer.maxlen - 10
        for i, obj in enumerate(buffer):
            img = obj['img']
            img = cv.cvtColor(img, cv.COLOR_BAYER_BG2BGR)
            rect = scale_rect(roi_rect, 3)
            x, y, w, h = rect
            cv.rectangle(img, (x, y), (x + w, y + h), (200, 127, 127), 1)
            cv.putText(img, 'Replay', (0, 50), 0, 2, (255, 255, 0), thickness=8)
            self.toLive(img)
            if i >= max_ctr:
                break

    def toLive(self, img: np.array):
        if self.streamer:
            self.streamer.push_frame(img)
        else:
            cv.imshow('frame', img)
            cv.waitKey(1)

    def runner(self):
        while True:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()
                self.process(frame)
            else:
                time.sleep(0.01)

    def run(self) -> Process:
        process = Process(target=self.runner, args=())
        process.start()
        return process

    def push_frame(self, frame: np.array):
        try:
            self.frame_queue.put_nowait(frame)
        except Full:
            # discard old ones to make room for the current frame
            self.frame_queue.get()
            self.frame_queue.get()
            self.frame_queue.put(frame)
