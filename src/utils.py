import time
import sys
import numpy as np


def expo(value, current_epoch, lam):

    return value * np.exp(-current_epoch / lam)


def static(value, current_epoch, total_epochs):

    return value


def linear(value, current_epoch, total_epochs):

    return (value * (total_epochs - current_epoch) / total_epochs) + 0.5


def progressbar(target, width=30, interval=0.01, idx_interval=10, use=True, mult=1):

    start = time.time()
    last_update = 0
    interval = interval
    total_width = 0

    target = list(target)
    iter_length = len(target)

    prev_total_width = 0

    for current, p in enumerate(target):

        if not use or current % idx_interval:
            yield p
            continue

        now = time.time()

        if (now - last_update) < interval:
            yield p
            continue

        prev_total_width = total_width
        sys.stdout.write("\b" * prev_total_width)
        sys.stdout.write("\r")

        numdigits = int(np.floor(np.log10(iter_length))) + 1
        barstr = '%%%dd/%%%dd [' % (numdigits, numdigits)
        bar = barstr % (current * mult, iter_length * mult)
        prog = float(current) / iter_length
        prog_width = int(width * prog)
        if prog_width > 0:
            bar += ('=' * (prog_width-1))
            if current < iter_length:
                bar += '>'
            else:
                bar += '='
        bar += ('.' * (width - prog_width))
        bar += ']'
        sys.stdout.write(bar)
        total_width = len(bar)

        if current:
            time_per_unit = (now - start) / current
        else:
            time_per_unit = 0
        eta = time_per_unit * (iter_length - current)
        info = ''
        if current < iter_length:
            info += ' - ETA: %ds' % eta
        else:
            info += ' - %ds' % (now - start)

        total_width += len(info)
        if prev_total_width > total_width:
            info += ((prev_total_width - total_width) * " ")

        sys.stdout.write(info)
        sys.stdout.flush()

        if current >= iter_length:
            sys.stdout.write("\n")

        last_update = now

        yield p

    else:

        if not use:
            pass
        else:
            sys.stdout.write("\b" * prev_total_width)
            sys.stdout.write("\r")

            numdigits = int(np.floor(np.log10(iter_length))) + 1
            barstr = '%%%dd/%%%dd [' % (numdigits, numdigits)
            bar = barstr % (iter_length * mult, iter_length * mult)
            prog = float(iter_length) / iter_length
            prog_width = int(width * prog)
            if prog_width > 0:
                bar += ('=' * (prog_width-1))
                bar += '='
            bar += ('.' * (width - prog_width))
            bar += ']'
            sys.stdout.write(bar)


class MultiPlexer(object):

    def __init__(self, array, times):

        self.array = np.asarray(array)
        self.times = times

        self.new_shape = list(self.array.shape)
        self.new_shape[0] *= times
        self.new_shape = tuple(self.new_shape)

    def __iter__(self):

        for i in range(self.times):

            for item in self.array:

                yield item

    @property
    def shape(self):
        return self.new_shape

    def mean(self, axis=None):

        if axis is None:
            return self.array.mean()
        return self.array.mean(axis=axis)