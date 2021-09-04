import time
import sys
import threading
import datetime
import numpy as np
import logging
import io
import configparser
from streamer import Streamer
import atexit
from utils import exit_handler
from post_process import Processor
import cv2 as cv
# logging.basicConfig(filename='logfile.log', level=logging.DEBUG)
# logging.basicConfig(level=logging.WARN)
from multiprocessing import Queue, Process


config = configparser.ConfigParser()
config.read('settings.ini')

processor = Processor(config)
processor.streamer = None
processor.run()
#cap = cv.VideoCapture('test2.mp4')
#cap = cv.VideoCapture('test_杨门工业区_20210822.ogv')
cap = cv.VideoCapture('indi_record_2021-08-22@15-01-55_F01750-18633.ser_F00001-16884.avi')

ctr = 0

while cap.isOpened():
    print(ctr)
    ctr += 1
    ret, frame = cap.read()
    #cv.imshow('live', frame)
    #frame = cv.resize(frame, (1304, 976))
    frame = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
    processor.push_frame(frame)
    time.sleep(0.04)


    #if cv.waitKey(30) & 0xFF == ord('q'):
    #    break




