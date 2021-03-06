from pydro.io import *
from pydro.train import *
from pydro.features import *
from pydro.core import *
from pydro.detection import *

import itertools

import scipy.misc

def train_test():
    model = LoadModel('tests/example.dpm')

    image = scipy.misc.imread('tests/000034.jpg')
    pyramid = BuildPyramid(image, model=model)

    filtered_model = model.Filter(pyramid)

    detections = [d for i,d in itertools.izip(xrange(1), filtered_model.Parse(-1))]
    assert detections[0].loss is None

    feature_vector = [build_feature_vector(d, belief=True, positive=True) for d in detections]

def loss_adjustment_test():
    model = LoadModel('tests/example.dpm')

    image = scipy.misc.imread('tests/000034.jpg')
    pyramid = BuildPyramid(image, model=model)

    def loss_adjustment (rule, score):
        return [Score(scale=s.scale, score=s.score+1) for s in score]

    filtered_model = model.Filter(pyramid, loss_adjustment=loss_adjustment)

    detections = [d for i,d in itertools.izip(xrange(1), filtered_model.Parse(-1))]
    print(detections[0].loss)
    print(detections[0].s)
    assert math.fabs(detections[0].loss - 9) < 1e-5

def neg_latent_test():
    model = LoadModel('tests/example.dpm')

    image = scipy.misc.imread('tests/000034.jpg')
    pyramid = BuildPyramid (image, model=model, interval=4)

    M = 1
    example = get_negative_latent_features (model, pyramid, M)

    assert len(example) == 2

    for entry in example:
        new_score = score_vector(entry)
        print(entry.score, entry.loss)
        assert math.fabs(entry.score - new_score) < 1e-4

def pos_latent_test():
    model = LoadModel('tests/example.dpm')

    image = scipy.misc.imread('tests/000034.jpg')
    pyramid = BuildPyramid (image, model=model, interval=5)

    def belief_adjustment (rule, score):
        return score

    def loss_adjustment (rule, score):
        return score

    M = 1
    example = get_positive_latent_features (model, pyramid, belief_adjustment, loss_adjustment, M)

    assert len(example) == 3

    for entry in example:
        new_score = score_vector(entry)
        print(entry.score, entry.loss)
        assert math.fabs(entry.score - new_score) < 1e-4

def overlap_loss_test():
    interval_fg = 5

    model = LoadModel('tests/example.dpm')

    image = scipy.misc.imread('tests/000034.jpg')
    pyramid_orig = BuildPyramid (image, model=model)
    filtered_model = model.Filter (pyramid_orig)
    detection = filtered_model.Parse(-1).next()

    bbox = __BBox__(x1=detection.x1, y1=detection.y1, x2=detection.x2, y2=detection.y2)

    pyramid = BuildPyramid (image, model=model, interval=interval_fg)

    loss_adjustment = overlap_loss_adjustment(model, pyramid, 0.5, 1, model.start.rules, bbox)
    belief_adjustment = overlap_loss_adjustment(model, pyramid, 0.7, -numpy.inf, model.start.rules, bbox)

    M = 1
    example = get_positive_latent_features (model, pyramid, belief_adjustment, loss_adjustment, M)

    assert len(example) == 3

    for entry in example:
        new_score = score_vector(entry)
        print(entry.score, entry.loss)
        assert math.fabs(entry.score - new_score) < 1e-4

def optimize_test():
    interval_fg = 5

    model = LoadModel('tests/example.dpm')

    image = scipy.misc.imread('tests/000034.jpg')
    pyramid_orig = BuildPyramid (image, model=model)
    filtered_model = model.Filter (pyramid_orig)
    detection = filtered_model.Parse(-1).next()

    bbox = __BBox__(x1=detection.x1, y1=detection.y1, x2=detection.x2, y2=detection.y2)

    pyramid = BuildPyramid (image, model=model, interval=interval_fg)

    loss_adjustment = overlap_loss_adjustment(model, pyramid, 0.5, 1, model.start.rules, bbox)
    belief_adjustment = overlap_loss_adjustment(model, pyramid, 0.7, -numpy.inf, model.start.rules, bbox)

    M = 1
    example = get_positive_latent_features (model, pyramid, belief_adjustment, loss_adjustment, M)
    assert len(example) == 3

    for entry in example:
        new_score = score_vector(entry)
        print(entry.score, entry.loss)
        assert math.fabs(entry.score - new_score) < 1e-4

    optimize (model, examples=[example], svm_c=0.001)
