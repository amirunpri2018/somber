import numpy as np
# import tensorflow as tf
import time
import logging
import cProfile

from progressbar import progressbar
from collections import defaultdict

logger = logging.getLogger(__name__)


def expo(value, current_epoch, lam):

    return value * np.exp(-current_epoch / lam)


def static(value, current_epoch, total_epochs):

    return value


class Som(object):

    def __init__(self, width, height, dim, learning_rates, lrfunc=expo, nbfunc=expo, sigma=None):

        if sigma is not None:
            self.sigma = sigma
        else:
            # Add small constant to sigma to prevent divide by zero for maps of size 2.
            self.sigma = (max(width, height) / 2.0) + 0.01

        self.lam = 0

        if type(learning_rates) != list:
            learning_rates = [learning_rates]

        self.learning_rates = np.array(learning_rates)

        self.width = width
        self.height = height
        self.map_dim = width * height

        self.weights = np.random.uniform(-0.1, 0.1, size=(self.map_dim, dim))
        self.data_dim = dim

        self.distance_grid = self._calculate_distance_grid()

        self._index_dict = {idx: (idx // self.height, idx % self.height) for idx in range(self.weights.shape[0])}
        self._coord_dict = defaultdict(dict)

        self.lrfunc = lrfunc
        self.nbfunc = nbfunc

        for k, v in self._index_dict.items():

            x_, v_ = v
            self._coord_dict[x_][v_] = k

        self.trained = False

    def train(self, X, num_epochs=10, batch_size=100):
        """
        Fits the SOM to some data for a number of epochs.
        As the learning rate is decreased proportionally to the number
        of epochs, incrementally training a SOM is not feasible.

        :param X: the data on which to train.
        :param num_epochs: The number of epochs to simulate
        :return: None
        """

        # Scaler ensures that the neighborhood radius is 0 at the end of training
        # given a square map.
        self.lam = num_epochs / np.log(self.sigma)

        # Local copy of learning rate.
        learning_rate = self.learning_rates

        bmus = []

        real_start = time.time()

        if np.ndim(X) == 2:
            X = np.resize(X, (num_batches * batch_size, X.shape[1]))
        elif np.ndim(X) == 3:
            X = np.resize(X, (num_batches * batch_size, X.shape[1], X.shape[2]))

        print(X.shape)

        for epoch in range(num_epochs):

            print("\nEPOCH: {0}/{1}".format(epoch+1, num_epochs))
            start = time.time()

            map_radius = self.nbfunc(self.sigma, epoch, self.lam)
            print("\nRADIUS: {0}".format(map_radius))
            bmu = self.epoch_step(X, map_radius, learning_rate, batch_size=batch_size)

            bmus.append(bmu)
            learning_rate = self.lrfunc(self.learning_rates, epoch, num_epochs)

            print("\nEPOCH TOOK {0:.2f} SECONDS.".format(time.time() - start))
            print("TOTAL: {0:.2f} SECONDS.".format(time.time() - real_start))

        self.trained = True

        return bmus

    def epoch_step(self, X, map_radius, learning_rate, batch_size):
        """
        A single example.

        :param X: a numpy array of examples
        :param map_radius: The radius at the current epoch, given the learning rate and map size
        :param learning_rate: The learning rate.
        :param batch_size: The batch size to use.
        :return: The best matching unit
        """

        # Calc once per epoch
        influences = self._distance_grid(map_radius) * learning_rate[0]
        influences = np.asarray([influences] * self.data_dim).transpose((1, 2, 0))

        # One accumulator per epoch
        all_activations = []

        # Make a batch generator.
        accumulator = np.zeros_like(self.weights)
        num_updates = 0

        num_batches = np.ceil(len(X) / batch_size).astype(int)

        for index in progressbar(range(num_batches), idx_interval=1, mult=batch_size):

            # Select the current batch.
            batch = X[index * batch_size: (index+1) * batch_size]

            update, differences = self._batch(batch, influences)

            all_activations.extend(np.sqrt(np.sum(np.square(differences), axis=2)))
            accumulator += update
            num_updates += 1

        self.weights += (accumulator / num_updates)

        return np.array(all_activations)

    def _distance_grid(self, radius):

        p = np.exp(-1.0 * self.distance_grid / (2.0 * radius ** 2)).reshape(self.map_dim, self.map_dim)

        return p

    def _batch(self, batch, influences):

        bmus, differences = self._get_bmus(batch)
        influences = influences[bmus, :]
        update = self._calculate_update(differences, influences).mean(axis=0)

        return update, differences

    def _calculate_update(self, input_vector, influence):
        """
        Updates the nodes, conditioned on the input vector,
        the influence, as calculated above, and the learning rate.

        :param input_vector: The input vector.
        :param influence: The influence the result has on each unit, depending on distance.
        """

        return input_vector * influence

    def _get_bmus(self, x):
        """
        Gets the best matching units, based on euclidean distance.

        :param x: The input vector
        :return: An integer, representing the index of the best matching unit.
        """

        differences = self._pseudo_distance(x, self.weights)
        distances = np.sqrt(np.sum(np.square(differences), axis=2))
        return np.argmin(distances, axis=1), differences

    def _pseudo_distance(self, X, weights):
        """
        Calculates the euclidean distance between an input and all the weights in range.

        :param x: The input.
        :param weights: An array of weights.
        :return: The distance from the input of each weight.
        """

        # Correct
        p = np.tile(X, (1, self.map_dim)).reshape((X.shape[0], self.map_dim, X.shape[1]))
        return p - weights

    def _calculate_distance_grid(self):

        distance_matrix = np.zeros((self.map_dim, self.map_dim))

        for i in range(self.map_dim):

            distance_matrix[i] = self._grid_dist(i).reshape(1, self.map_dim)

        return distance_matrix

    def _grid_dist(self, index):

        rows = self.height
        cols = self.width

        # bmu should be an integer between 0 to no_nodes
        node_col = int(index % cols)
        node_row = int(index / cols)

        r = np.arange(0, rows, 1)[:, np.newaxis]
        c = np.arange(0, cols, 1)
        dist2 = (r-node_row)**2 + (c-node_col)**2

        return dist2.ravel()

    def predict(self, X):
        """
        Predicts node identity for input data.
        Similar to a clustering procedure.

        :param x: The input data.
        :return: A list of indices
        """

        # Return the indices of the BMU which matches the input data most
        bmus, _ = self._get_bmus(X)
        return bmus

    def predict_distance(self, X):

        _, differences = self._get_bmus(X)
        return np.sqrt(np.sum(np.square(differences), axis=2))

    def map_weights(self):
        """
        Retrieves the grid as a list of lists of weights. For easy visualization.

        :return: A three-dimensional Numpy array of values (width, height, data_dim)
        """

        mapped_weights = []

        for x in range(self.width):
            x *= self.height
            temp = []
            for y in range(self.height):
                temp.append(self.weights[x + y])

            mapped_weights.append(temp)

        return np.array(mapped_weights)

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    colors = np.array(
         [[0., 0., 0.],
          [0., 0., 1.],
          [0., 0., 0.5],
          [0.125, 0.529, 1.0],
          [0.33, 0.4, 0.67],
          [0.6, 0.5, 1.0],
          [0., 1., 0.],
          [1., 0., 0.],
          [0., 1., 1.],
          [1., 0., 1.],
          [1., 1., 0.],
          [1., 1., 1.],
          [.33, .33, .33],
          [.5, .5, .5],
          [.66, .66, .66]])

    colors = np.array(colors)

    '''colors = []

    for x in range(10):
        for y in range(10):
            for z in range(10):
                colors.append((x/10, y/10, z/10))

    colors = np.array(colors, dtype=float)'''
    # colors = np.vstack([colors, colors, colors, colors, colors, colors, colors, colors])

    '''addendum = np.arange(len(colors) * 10).reshape(len(colors) * 10, 1) / 10

    colors = np.array(colors)
    colors = np.repeat(colors, 10).reshape(colors.shape[0] * 10, colors.shape[1])

    print(colors.shape, addendum.shape)

    colors = np.hstack((colors,addendum))
    print(colors.shape)'''

    color_names = \
        ['black', 'blue', 'darkblue', 'skyblue',
         'greyblue', 'lilac', 'green', 'red',
         'cyan', 'violet', 'yellow', 'white',
         'darkgrey', 'mediumgrey', 'lightgrey']

    s = Som(30, 30, 3, [1.0])
    start = time.time()
    bmus = s.train(colors, num_epochs=100)



    # bmu_history = np.array(bmu_history).T
    print("Took {0} seconds".format(time.time() - start))

    '''from visualization.umatrix import UMatrixView

    view = UMatrixView(500, 500, 'dom')
    view.create(s.weights, colors, s.width, s.height, bmus[-1])
    view.save("junk_viz/_{0}.svg".format(0))

    print("Made {0}".format(0))'''