from pydro.detection import FilterPyramid, DeformationCost, Score

import itertools
import numpy
from collections import namedtuple
import weakref

__all__ = [
    'Offset',
    'Block',
    'Def',
    'DeformationRule',
    'Features',
    'Filter',
    'Loc',
    'Model',
    'Rule',
    'Stats',
    'StructuralRule',
    'Symbol',
    'FilteredSymbol',
    'FilteredStructuralRule',
    'FilteredDeformationRule',
    'TreeNode',
    'Leaf',
]

TreeRoot = namedtuple('TreeRoot', 'x1,x2,y1,y2,s,child,loss,model')
TreeNode = namedtuple('TreeNode', 'x,y,l,symbol,ds,s,children,rule,loss')
Leaf = namedtuple('Leaf', 'x1,x2,y1,y2,scale,x,y,l,s,ds,symbol')


class Model(object):

    def __init__(self, clss, year, note, start, maxsize, minsize,
                 interval, sbin, thresh, type, features, stats):
        self.clss = clss
        self.year = year
        self.note = note
        self.start = start
        self.maxsize = maxsize
        self.minsize = minsize
        self.interval = interval
        self.sbin = sbin
        self.thresh = thresh
        self.type = type
        self.features = features
        self.stats = stats

    def Filter(self, pyramid, loss_adjustment=None):
        return FilteredModel(self, pyramid, loss_adjustment)

    def GetBlocks(self):
        return self.start.GetBlocks()


class FilteredModel (Model):

    def __init__(self, model, pyramid, loss_adjustment):
        super(FilteredModel, self).__init__(
            clss=model.clss,
            year=model.year,
            note=model.note,
            start=model.start,
            maxsize=model.maxsize,
            minsize=model.minsize,
            interval=model.interval,
            sbin=model.sbin,
            thresh=model.thresh,
            type=model.type,
            features=model.features,
            stats=model.stats,
        )

        self.size = self.start.GetFilteredSize(pyramid)
        self.loss_adjustment = loss_adjustment
        self.pyramid = pyramid

        self.start = model.start.Filter(self)

    def Filter(self, loss_adjustment=None):
        return FilteredModel(self, self.pyramid, self.loss_adjustment)

    def Parse(self, threshold):
        X = numpy.array([], dtype=numpy.uint32)
        Y = numpy.array([], dtype=numpy.uint32)
        L = numpy.array([], dtype=numpy.uint32)
        S = numpy.array([], dtype=numpy.float32)
        for pos, level in enumerate(self.start.score):
            if isinstance(level.score, numpy.ndarray):
                Yi, Xi = numpy.where(level.score > threshold)
                Si = level.score[Yi, Xi].flatten()
                Li = pos * numpy.ones(Si.shape, dtype=numpy.uint32)
                X = numpy.hstack((X, Xi))
                Y = numpy.hstack((Y, Yi))
                S = numpy.hstack((S, Si))
                L = numpy.hstack((L, Li))

        order = list(enumerate(S))
        order.sort(key=lambda k: -k[1])
        order = numpy.array([o[0] for o in order], dtype=numpy.uint32)

        X = X[order]
        Y = Y[order]
        L = L[order]
        S = S[order]
        X.flags.writeable = False
        Y.flags.writeable = False
        L.flags.writeable = False
        S.flags.writeable = False

        detections = []

        assert len(X) == len(Y)
        assert len(X) == len(L)
        assert len(X) == len(S)
        for x, y, l, s in itertools.izip(X, Y, L, S):
            parsed = self.start.Parse(x=x, y=y, l=l, s=s, ds=0, model=self)
            detwindow = parsed.rule.detwindow
            shiftwindow = parsed.rule.shiftwindow
            scale = self.pyramid.sbin / self.start.score[parsed.l].scale

            x1 = (parsed.x - shiftwindow[
                  1] - self.pyramid.padx * (1 << parsed.ds)) * scale
            y1 = (parsed.y - shiftwindow[
                  0] - self.pyramid.pady * (1 << parsed.ds)) * scale
            x2 = x1 + detwindow[1] * scale - 1
            y2 = y1 + detwindow[0] * scale - 1

            root = TreeRoot(
                model=self,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                s=parsed.s,
                child=parsed,
                loss=parsed.loss,
            )

            yield root


class Filter(object):

    _p = numpy.array([
        9, 8, 7, 6, 5, 4, 3, 2, 1,
        0, 17, 16, 15, 14, 13, 12, 11, 10,
        18, 26, 25, 24, 23, 22, 21, 20, 19,
        29, 30, 27, 28,
        31,
    ])
    _p.flags.writeable = False

    def __init__(self, blocklabel, size, flip, symbol):
        self.blocklabel = blocklabel
        self.size = size
        self.flip = flip
        self.symbol = symbol

        if self.flip:
            self._w = self.blocklabel.w[:, ::-1, Filter._p]
        else:
            self._w = self.blocklabel.w

    def GetFeatures(self, model, node):
        fy = node.y - model.pyramid.pady * ((1 << node.ds) - 1)
        fx = node.x - model.pyramid.padx * ((1 << node.ds) - 1)

        feat = model.pyramid.levels[node.l].features[
            fy:fy + self.size[0], fx:fx + self.size[1], :]
        if self.flip:
            feat = feat[:, :, Filter._p]

        return {self.blocklabel: feat.flatten()}

    def GetBlocks(self):
        return [self.blocklabel]

    def SetSymbol(self, symbol):
        self.symbol = weakref.ref(symbol)

    def GetParameters(self):
        return self._w


class Rule(object):

    def __init__(self, type, lhs, rhs, detwindow, shiftwindow, i,
                 offset, loc, blocks, metadata):
        self.type = type
        if isinstance(lhs, Symbol):
            self.lhs = weakref.ref(lhs)
        else:
            self.lhs = lhs
        self.rhs = rhs
        self.detwindow = detwindow
        self.shiftwindow = shiftwindow
        self.i = i
        self.offset = offset
        self.loc = loc
        self.blocks = blocks
        self.metadata = metadata

    def __repr__(self):
        return '%s: %s' % (self.type, super(Rule, self).__repr__())

    def SetLHS(self, lhs):
        self.lhs = weakref.ref(lhs)

    def GetFilteredSize(self, pyramid):
        size_pyramid = [(1, 1) for level in pyramid.levels]

        for symbol in self.rhs:
            symbol_size_pyramid = symbol.GetFilteredSize(pyramid)
            assert len(size_pyramid) == len(symbol_size_pyramid)

            for i in xrange(len(symbol_size_pyramid)):
                ymax, xmax = size_pyramid[i]
                ycurr, xcurr = symbol_size_pyramid[i]

                size_pyramid[i] = (max(ymax, ycurr), max(xmax, xcurr))

        return size_pyramid

    def GetFeatures(self, model, node):
        offset_features = self.offset.GetFeatures(model, node)
        loc_features = self.loc.GetFeatures(model, node)
        children_features = [child.symbol.GetFeatures(model, child)
                             for child in node.children]

        features = {}

        for k in offset_features:
            assert k not in features
            features[k] = offset_features[k]

        for k in loc_features:
            assert k not in features
            features[k] = loc_features[k]

        for child_features in children_features:
            for k in child_features:
                assert k not in features
                features[k] = child_features[k]

        return features

    def GetBlocks(self):
        blocks = self.offset.GetBlocks() + self.loc.GetBlocks()
        for symbol in self.rhs:
            blocks += symbol.GetBlocks()

        return blocks


class DeformationRule(Rule):

    def __init__(self, type, lhs, rhs, detwindow, shiftwindow, i,
                 offset, df, loc, blocks, metadata):
        super(DeformationRule, self).__init__(
            type, lhs, rhs, detwindow, shiftwindow, i, offset, loc, blocks, metadata
        )

        self.df = df

    def Filter(self, model):
        return FilteredDeformationRule(self, model)

    def GetFeatures(self, model, node):
        features = super(DeformationRule, self).GetFeatures(model, node)

        df_features = self.df.GetFeatures(model, node)

        for k in df_features:
            assert k not in features
            features[k] = df_features[k]

        return features

    def GetBlocks(self):
        blocks = super(DeformationRule, self).GetBlocks()

        blocks += self.df.GetBlocks()

        return blocks


class FilteredDeformationRule(DeformationRule):

    def __init__(self, deformation_rule, model):
        super(FilteredDeformationRule, self).__init__(
            type=deformation_rule.type,
            lhs=deformation_rule.lhs,
            rhs=deformation_rule.rhs,
            detwindow=deformation_rule.detwindow,
            shiftwindow=deformation_rule.shiftwindow,
            i=deformation_rule.i,
            offset=deformation_rule.offset,
            loc=deformation_rule.loc,
            df=deformation_rule.df,
            blocks=deformation_rule.blocks,
            metadata=deformation_rule.metadata,
        )

        self.rhs = [s.Filter(model) for s in deformation_rule.rhs]

        def_w = self.df.GetParameters()

        assert len(self.rhs) == 1

        score = self.rhs[0].score

        bias = self.offset.GetParameters()
        loc_w = self.loc.GetParameters()

        loc_f = numpy.zeros(
            (3, len(model.pyramid.levels)), dtype=numpy.float32)
        loc_f[0, 0:model.pyramid.interval] = 1
        loc_f[1, model.pyramid.interval:2 * model.pyramid.interval] = 1
        loc_f[2, 2 * model.pyramid.interval:] = 1
        loc_f.flags.writeable = False

        loc_scores = loc_w.dot(loc_f)

        ax, bx, ay, by = def_w.flatten().tolist()

        assert len(loc_scores.flatten()) == len(score)
        deformations = [
            DeformationCost(bias + s + ss.score, ax, bx, ay, by, 4)
            for s, ss in itertools.izip(loc_scores.flatten(), score)
        ]

        assert len(score) == len(deformations)
        self.score = [
            Score(scale=s.scale, score=d[0])
            for s, d in itertools.izip(score, deformations)
        ]
        self.Ix = [d[1] for d in deformations]
        self.Iy = [d[2] for d in deformations]

        if model.loss_adjustment:
            self.score_original = self.score
            self.score = model.loss_adjustment(deformation_rule, self.score)

    def Parse(self, x, y, l, s, ds, model):
        Ix = self.Ix[l]
        Iy = self.Iy[l]

        nvp_y = y - model.pyramid.pady * ((1 << ds) - 1)
        nvp_x = x - model.pyramid.padx * ((1 << ds) - 1)

        rhs_nvp_x = Ix[nvp_y, nvp_x]
        rhs_nvp_y = Iy[nvp_y, nvp_x]

        rhs_x = rhs_nvp_x + model.pyramid.padx * ((1 << ds) - 1)
        rhs_y = rhs_nvp_y + model.pyramid.pady * ((1 << ds) - 1)

        symbol, = self.rhs

        nvp_x = rhs_x - model.pyramid.padx * ((1 << ds) - 1)
        nvp_y = rhs_y - model.pyramid.pady * ((1 << ds) - 1)
        rhs_s = symbol.score[l].score[nvp_y, nvp_x]

        children = [symbol.Parse(
            x=rhs_x,
            y=rhs_y,
            l=l,
            ds=ds,
            s=rhs_s,
            model=model,
        )]

        return children


class StructuralRule(Rule):

    def __init__(self, type, lhs, rhs, detwindow, shiftwindow, i, anchor,
                 offset, loc, blocks, metadata):
        super(StructuralRule, self).__init__(
            type, lhs, rhs, detwindow, shiftwindow, i, offset, loc, blocks, metadata
        )

        self.anchor = anchor

    def Filter(self, model):
        return FilteredStructuralRule(self, model)


class FilteredStructuralRule(StructuralRule):

    def __init__(self, structural_rule, model):
        super(FilteredStructuralRule, self).__init__(
            type=structural_rule.type,
            lhs=structural_rule.lhs,
            rhs=structural_rule.rhs,
            detwindow=structural_rule.detwindow,
            shiftwindow=structural_rule.shiftwindow,
            i=structural_rule.i,
            anchor=structural_rule.anchor,
            offset=structural_rule.offset,
            loc=structural_rule.loc,
            blocks=structural_rule.blocks,
            metadata=structural_rule.metadata,
        )

        self.rhs = [s.Filter(model) for s in structural_rule.rhs]

        bias = self.offset.GetParameters() * model.features.bias
        loc_w = self.loc.GetParameters()

        loc_f = numpy.zeros((3, len(model.pyramid.levels)))
        loc_f[0, 0:model.pyramid.interval] = 1
        loc_f[1, model.pyramid.interval:2 * model.pyramid.interval] = 1
        loc_f[2, 2 * model.pyramid.interval:] = 1
        loc_f.flags.writeable = False

        loc_scores = loc_w.dot(loc_f).flatten()

        assert len(model.size) == len(loc_scores.flatten())
        self.score = [
            float(bias + loc_score) * numpy.ones(size, dtype=numpy.float32)
            for size, loc_score
            in itertools.izip(model.size, loc_scores.flatten())
        ]

        assert len(self.anchor) == len(self.rhs)
        for anchor, symbol in itertools.izip(self.anchor, self.rhs):
            ax, ay, ds = anchor

            step = 2 ** ds

            virtpadx = (step - 1) * model.pyramid.padx
            virtpady = (step - 1) * model.pyramid.pady

            startx = ax - virtpadx + 1
            starty = ay - virtpady + 1

            score = [s.score for s in symbol.score]

            for i in xrange(len(score)):
                level = i - model.pyramid.interval * ds

                if level >= 0:
                    endy = min(
                        score[level].shape[0],
                        starty + step * (self.score[i].shape[0] - 1)
                    )

                    endx = min(
                        score[level].shape[1],
                        startx + step * (self.score[i].shape[1] - 1)
                    )

                    iy = numpy.arange(starty, endy + 1, step)
                    oy = (iy < 1).sum()
                    iy = iy[numpy.where(iy >= 1)].flatten()

                    ix = numpy.arange(startx, endx + 1, step)
                    ox = (ix < 1).sum()
                    ix = ix[numpy.where(ix >= 1)].flatten()

                    sp = score[level][iy - 1, :][:, ix - 1]
                    sz = sp.shape

                    stmp = (-numpy.inf * numpy.ones(self.score[i].shape)).astype(
                        numpy.float32)
                    assert oy >= 0
                    assert ox >= 0
                    assert oy + sz[0] - 1 < stmp.shape[0]
                    assert ox + sz[1] - 1 < stmp.shape[1]
                    stmp[oy:oy + sz[0], ox:ox + sz[1]] = sp

                    self.score[i] += stmp
                else:
                    self.score[i][:] = -numpy.inf

        for s in self.score:
            s.flags.writeable = False

        assert len(model.pyramid.levels) == len(self.score)
        self.score = [
            Score(scale=l.scale, score=s)
            for l, s in itertools.izip(model.pyramid.levels, self.score)
        ]

        if model.loss_adjustment:
            self.score_original = self.score
            self.score = model.loss_adjustment(structural_rule, self.score)

    def Parse(self, x, y, l, s, ds, model):
        assert len(self.anchor) == len(self.rhs)
        children = []
        for anchor, symbol in itertools.izip(self.anchor, self.rhs):
            ax, ay, ads = anchor

            rhs_x = x * (1 << ads) + ax
            rhs_y = y * (1 << ads) + ay
            rhs_l = l - model.pyramid.interval * ads

            rhs_ds = ds + ads

            nvp_y = rhs_y - model.pyramid.pady * ((1 << rhs_ds) - 1)
            nvp_x = rhs_x - model.pyramid.padx * ((1 << rhs_ds) - 1)

            rhs_s = symbol.score[rhs_l].score[nvp_y, nvp_x]

            children += [
                symbol.Parse(
                    x=rhs_x,
                    y=rhs_y,
                    l=rhs_l,
                    s=rhs_s,
                    ds=rhs_ds,
                    model=model
                )
            ]

        return children


class Symbol(object):

    def __init__(self, type, filter, rules=[]):
        if type == 'T':
            assert filter is not None
        self.type = type
        self.filter = filter
        self.rules = rules

    """
    def __repr__(self):
        print(self.__dict__)
        return '%s\t%s' % (self.type, super(Symbol, self).__repr__())
    """

    def Filter(self, model):
        symbol = FilteredSymbol(self, model)

        return symbol

    def GetFeatures(self, model, node):
        assert self == node.symbol

        if self.type == 'T':
            assert isinstance(node, Leaf)
            return self.filter.GetFeatures(model, node)
        else:
            assert isinstance(node, TreeNode)
            return node.rule.GetFeatures(model, node)

    def GetBlocks(self):
        if self.type == 'T':
            return self.filter.GetBlocks()
        else:
            blocks = []
            for rule in self.rules:
                blocks += rule.GetBlocks()
            return blocks

    def GetFilteredSize(self, pyramid):
        if self.type == 'T':
            return [(
                level.features.shape[
                    0] - self.filter.GetParameters().shape[0] + 1,
                level.features.shape[
                    1] - self.filter.GetParameters().shape[1] + 1,
            ) for level in pyramid.levels]

        else:
            size_pyramid = [(1, 1) for level in pyramid.levels]

            for rule in self.rules:
                rule_size_pyramid = rule.GetFilteredSize(pyramid)
                assert len(rule_size_pyramid) == len(size_pyramid)

                for i in xrange(len(rule_size_pyramid)):
                    ymax, xmax = size_pyramid[i]
                    ycurr, xcurr = rule_size_pyramid[i]

                    size_pyramid[i] = (max(ymax, ycurr), max(xmax, xcurr))

            return size_pyramid


class FilteredSymbol(Symbol):

    def __init__(self, symbol, model):
        super(FilteredSymbol, self).__init__(
            type=symbol.type,
            filter=symbol.filter,
            rules=symbol.rules,
        )

        if self.filter is not None:
            if isinstance(symbol, FilteredSymbol):
                self.score = symbol.score
            else:
                filter = self.filter.GetParameters()
                self.score = FilterPyramid(model.pyramid, filter, model.size)

            self.rules = []
        else:
            self.rules = [r.Filter(model) for r in symbol.rules]

            self.score = self.rules[0].score
            for rule in self.rules[1:]:
                self.score = [Score(
                    scale=level.scale,
                    score=numpy.max(
                        numpy.dstack((level.score, f.score)), axis=2),
                )
                    for level, f in itertools.izip(self.score, rule.score)]

        for s in self.score:
            s.score.flags.writeable = False

        assert self.score is not None

    def Parse(self, x, y, l, s, ds, model):
        if self.type == 'T':
            scale = model.pyramid.sbin / self.score[l].scale

            x1 = (x - model.pyramid.padx * (1 << ds)) * scale
            y1 = (y - model.pyramid.pady * (1 << ds)) * scale
            x2 = x1 + self.filter.GetParameters().shape[1] * scale - 1
            y2 = y1 + self.filter.GetParameters().shape[0] * scale - 1

            leaf = Leaf(
                x1=x1,
                x2=x2,
                y1=y1,
                y2=y2,
                x=x,
                y=y,
                l=l,
                s=s,
                ds=ds,
                symbol=self,
                scale=scale,
            )

            return leaf
        else:
            selected_rule = None
            for rule in self.rules:
                nvp_y = y - model.pyramid.pady * ((1 << ds) - 1)
                nvp_x = x - model.pyramid.padx * ((1 << ds) - 1)

                score = rule.score[l].score[nvp_y, nvp_x]

                if score == s:
                    selected_rule = rule
                    break
            if selected_rule is None:
                raise Exception('Rule argmax not found')
            rule = selected_rule

            children = rule.Parse(x=x, y=y, l=l, s=s, ds=ds, model=model)
            loss = None if model.loss_adjustment is None else sum(child.loss for child in children if isinstance(child, TreeNode)) + \
                score - rule.score_original[l].score[nvp_y, nvp_x]
            if loss is not None:
                s -= loss

            node = TreeNode(
                x=x,
                y=y,
                l=l,
                ds=ds,
                s=s,
                symbol=self,
                rule=selected_rule,
                children=children,
                loss=loss,
            )

            return node

    def __repr__(self):
        return '%s\t%s' % (self.type, '\n\t'.join(
            str(type(r)) for r in self.rules
        ))


class Block(object):

    def __init__(self, w, lb, learn, reg_mult, dim, type):
        self.w = w
        self.lb = lb
        self.learn = learn
        self.reg_mult = reg_mult
        self.dim = dim
        self.type = type


class Features(object):

    def __init__(self, sbin, dim, truncation_dim, extra_octave, bias):
        self.sbin = sbin
        self.dim = dim
        self.truncation_dim = truncation_dim
        self.extra_octave = extra_octave
        self.bias = bias


class Stats(object):

    def __init__(self, slave_problem_time, data_mining_time, pos_latent_time,
                 filter_usage):
        self.slave_problem_time = slave_problem_time
        self.data_mining_time = data_mining_time
        self.pos_latent_time = pos_latent_time
        self.filter_usage = filter_usage


class Def(object):

    def __init__(self, blocklabel, flip):
        self.blocklabel = blocklabel
        self.flip = flip

        self._w = self.blocklabel.w.copy()
        if self.flip:
            self._w[0][1] *= -1

    def GetFeatures(self, model, node):
        child_node, = node.children

        dx = node.x - child_node.x
        dy = node.y - child_node.y

        df = numpy.array([-(dx ** 2), -dx, -(dy ** 2), -dy])
        if self.flip:
            df[1] *= -1

        df.flags.writeable = False

        return {self.blocklabel: df}

    def GetBlocks(self):
        return [self.blocklabel]

    def GetParameters(self):
        return self._w


class Loc(object):

    def __init__(self, blocklabel):
        self.blocklabel = blocklabel

    def GetFeatures(self, model, node):
        loc_f = numpy.zeros((3,))
        if node.l < model.pyramid.interval:
            loc_f[0] = 1
        elif node.l < 2 * model.pyramid.interval:
            loc_f[1] = 1
        else:
            loc_f[2] = 1

        loc_f.flags.writeable = False

        return {self.blocklabel: loc_f}

    def GetBlocks(self):
        return [self.blocklabel]

    def GetParameters(self):
        return self.blocklabel.w


class Offset(object):

    def __init__(self, blocklabel):
        self.blocklabel = blocklabel

    def GetFeatures(self, model, node):
        bias = numpy.array([model.features.bias])
        bias.flags.writeable = False

        return {self.blocklabel: bias}

    def GetBlocks(self):
        return [self.blocklabel]

    def GetParameters(self):
        return self.blocklabel.w
