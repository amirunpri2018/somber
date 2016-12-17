import numpy as np
import logging
import time
import cProfile

from som import Som
from progressbar import progressbar

logging.basicConfig(level=logging.INFO)


class THSom(Som):

    def __init__(self, width, height, dim, learning_rates, beta):

        super().__init__(width, height, dim, learning_rates)
        # self.temporal_weights = np.random.uniform(0.0, 1.0, (self.map_dim, self.map_dim))
        self.temporal_weights = np.zeros((self.map_dim, self.map_dim))
        self.const_dim = np.sqrt(self.data_dim)
        self.beta = beta

    def epoch_step(self, X, map_radius, learning_rates, batch_size):
        """
        A single example.

        :param X: a numpy array of examples
        :param map_radius: The radius at the current epoch, given the learning rate and map size
        :param learning_rate: The learning rate.
        :param batch_size: The batch size
        :return: The best matching unit
        """

        alpha, zeta = learning_rates
        # One accumulator per epoch
        influences = self._distance_grid(map_radius) * alpha
        influences = np.asarray([influences] * self.data_dim).transpose((1, 2, 0))

        num_batches = np.ceil(len(X) / batch_size).astype(int)

        # Parallel timelines
        for index in progressbar(range(num_batches), idx_interval=1, mult=batch_size):

            # Select the current batch.
            current = X[index * batch_size: (index+1) * batch_size]

            # Initial previous activation
            prev_activations = np.zeros((batch_size, self.map_dim))
            prev_bmu = np.zeros((batch_size,), dtype=int)

            for idx in range(current.shape[1]):

                column = current[:, idx, :]

                bmu_theta, prev_activations, spatial = self._get_bmus(column,
                                                                      y=prev_activations,
                                                                      temporal_update=self.temporal_weights)

                spatial_update = self._calculate_update(spatial, influences[bmu_theta, :])
                temporal_update = self._temporal_update(batch_size, self.beta, prev_bmu=prev_bmu, bmu=bmu_theta, zeta=zeta)

                self.weights = spatial_update.mean(axis=0)
                self.temporal_weights += temporal_update.sum(axis=0)

                self.weights = self.weights.clip(0.0, 1.0)
                self.temporal_weights = self.temporal_weights.clip(0.0, 1.0)

                prev_bmu = bmu_theta

    def _get_bmus(self, x, **kwargs):
        """
        Gets the best matching units, based on euclidean distance.

        :param x: The input vector
        :return: An integer, representing the index of the best matching unit.
        """

        y = kwargs['y']
        spatial_differences = self._pseudo_distance(x, self.weights)

        # TODO: niet verwijderen, domme

        temporal_differences = []

        for z in range(len(x)):

            tempo_ = []

            for i in range(self.map_dim):

                temp = []

                for h in range(self.map_dim):

                    temp.append(y[z, h] * self.temporal_weights[i, h])

                tempo_.append(np.sum(temp))

            temporal_differences.append(tempo_)

        temporal_differences = np.array(temporal_differences)

        differences = (self.const_dim - np.sqrt(np.sum(np.square(spatial_differences), axis=2))) + temporal_differences
        differences = (differences.T / differences.max(axis=1)).T

        return np.argmax(differences, axis=1), differences, spatial_differences

    def _temporal_update(self, batch_size, beta, prev_bmu, bmu, zeta):
        """
        :param tempo:
        :param mintempo:
        :param prev_bmu:
        :return:
        """

        # Changed freeze of current state.
        update = -np.tile(zeta * (self.temporal_weights + beta), (batch_size, 1)).reshape((batch_size, self.map_dim, self.map_dim))
        update[np.arange(len(prev_bmu)), bmu, prev_bmu] = zeta * (1.0 - (self.temporal_weights[bmu, prev_bmu] + beta))

        return update

    def predict(self, X):
        """
        Predicts node identity for input data.
        Similar to a clustering procedure.

        :param x: The input data.
        :return: A list of indices
        """

        # Start with a clean buffer.

        prev_activations = np.zeros((X.shape[0], self.map_dim))

        all_bmus = []
        temporal_sum = self.temporal_weights.sum(axis=0)

        for idx in range(X.shape[1]):

            column = X[:, idx, :]
            bmus, prev_activations, _, _ = self._get_bmus(column, y=prev_activations, temporal_sum=temporal_sum)

            all_bmus.append(bmus)

        return np.array(all_bmus).T

    def assign_exemplar(self, exemplars, names=()):

        exemplars = np.array(exemplars)
        distances = self._pseudo_distance(exemplars, self.weights)
        distances = np.sum(np.square(distances), axis=2)

        if not names:
            return distances.argmax(axis=0).reshape((self.width, self.height))
        else:
            return [names[x] for x in distances.argmax(axis=0)]


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    colors = np.array(
         [[1., 0., 1.],
          [0., 0., 0.],
          [0., 0., 1.],
          [0., 0., 0.5],
          [0.125, 0.529, 1.0],
          [0.33, 0.4, 0.67],
          [0.6, 0.5, 1.0],
          [0., 1., 0.],
          [1., 0., 0.],
          [0., 1., 1.],
          [1., 1., 0.],
          [1., 1., 1.],
          [.33, .33, .33],
          [.5, .5, .5],
          [.66, .66, .66]])

    data = np.tile(colors, (100, 1, 1))

    colorpicker = np.arange(len(colors))

    data = colors[np.random.choice(colorpicker, size=15)]
    data = np.array([data] * 1000)
    print(data.shape)

    s = THSom(30, 30, 3, [1.0, 0.03], 0.01)
    start = time.time()
    cProfile.run("s.train(data, num_epochs=10, batch_size=1)")

    # bmu_history = np.array(bmu_history).T
    print("Took {0} seconds".format(time.time() - start))