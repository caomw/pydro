from pydro.io import *
from pydro.features import *

import scipy.misc

def parse_small_test():
    model = LoadModel('tests/example.dpm')
    model.start.rules = model.start.rules[:1]
    model.start.rules[0].rhs = model.start.rules[0].rhs[1:2]
    model.start.rules[0].anchor = model.start.rules[0].anchor[1:2]

    image = scipy.misc.imread('tests/000034.jpg')
    pyramid = BuildPyramid(image, model.sbin, model.interval, model.features.extra_octave, model.maxsize[1], model.maxsize[0])

    filtered_model = model.Filter(pyramid)

    detections = filtered_model.Parse(-2, 1)

def parse_test():
    model = LoadModel('tests/example.dpm')

    image = scipy.misc.imread('tests/000034.jpg')
    pyramid = BuildPyramid(image, model.sbin, model.interval, model.features.extra_octave, model.maxsize[1], model.maxsize[0])

    filtered_model = model.Filter(pyramid)

    detections = filtered_model.Parse(-2, 1)

