import logging
import json
import numpy as np

from .som import Som
from ..utils import expo, linear, np_min, np_max
from functools import reduce

logger = logging.getLogger(__name__)


class Sequential(Som):
    """
    A base class for sequential SOMs, removing some code duplication.

    Not usable as a stand-alone class
    """

    def __init__(self,
                 map_dim,
                 data_dim,
                 learning_rate,
                 sigma,
                 lrfunc=expo,
                 nbfunc=expo,
                 min_max=np_min,
                 influence_size=None):
        """
        A base class for sequential SOMs, removing some code duplication.

        :param map_dim: A tuple describing the MAP size.
        :param data_dim: The dimensionality of the input matrix.
        :param learning_rate: The learning rate.
        :param sigma: The neighborhood factor.
        :param lrfunc: The function used to decrease the learning rate.
        :param nbfunc: The function used to decrease the neighborhood
        :param min_max: The function used to determine the winner.
        :param distance_function: The function used to do distance calculation.
        Euclidean by default.
        :param influence_size: The size of the influence matrix.
        Usually reverts to data_dim, but can be
        larger.
        """
        super().__init__(map_dim,
                         data_dim,
                         learning_rate,
                         sigma,
                         lrfunc,
                         nbfunc,
                         min_max,
                         influence_size=influence_size)

    def _init_prev(self, X):
        """
        A safe initialization for the first previous value.

        :param X: The input data.
        :return: A matrix of the appropriate size for simulating contexts.
        """
        return np.zeros((X.shape[1], self.weight_dim))

    def _create_batches(self, X, batch_size):
        """
        Create subsequences out of a sequential piece of data.

        Assumes ndim(X) == 2.

        This function will append zeros to the end of your data to make
        sure all batches even-sized.

        :param X: A numpy array, representing your input data.
        Must have 2 dimensions.
        :param batch_size: The desired batch size.
        :return: A batched version of your data and a normed version of these batches.
        """

        self.progressbar_interval = 1
        self.progressbar_mult = batch_size

        self.w_norm = np.ones((1, self.weights.shape[0]))
        self.m_norm = np.ones((batch_size, 1))

        print(self.w_norm.shape, self.m_norm.shape)

        max_x = int(np.ceil(X.shape[0] / batch_size))
        # This line first resizes the data to
        # (batch_size, len(X) / batch_size, data_dim)
        if X.shape[0] % batch_size == 0:
            X = np.reshape(X, (batch_size, X.shape[0] // batch_size, X.shape[1]))
        else:
            X = np.resize(X, (batch_size, max_x, X.shape[1]))
        # Transposes it to (len(X) / batch_size, batch_size, data_dim)
        return X.transpose((1, 0, 2)), np.sum(np.square(X), axis=2).transpose()

    def forward(self, x, x_n, **kwargs):

        pass

    def _predict_base(self, X):
        """
        Predict distances to some input data.

        :param X: The input data.
        :return: An array of arrays, representing the activation
        each node has to each input.
        """
        X = self._create_batches(X, len(X))
        X = np.asarray(X, dtype=np.float32)

        distances = []

        prev = self._init_prev(X)

        for x in X:
            prev = self.forward(x, prev_activation=prev)
            distances.extend(prev)

        return np.array(distances, dtype=np.float32)


class Recursive(Sequential):

    def __init__(self,
                 map_dim,
                 data_dim,
                 learning_rate,
                 alpha,
                 beta,
                 sigma=None,
                 lrfunc=expo,
                 nbfunc=expo):
        """
        A recursive SOM.

        A recursive SOM models sequences through context dependence by not only
        storing the exemplars in weights, but also storing which exemplars
        preceded them. Because of this organization, the SOM can recursively
        "remember" short sequences, which makes it attractive for simple
        sequence problems, e.g. characters or words.

        :param map_dim: A tuple of map dimensions,
        e.g. (10, 10) instantiates a 10 by 10 map.
        :param data_dim: The data dimensionality.
        :param learning_rate: The learning rate, which is decreased
        according to some function.
        :param lrfunc: The function to use in decreasing the learning rate.
        The functions are defined in utils. Default is exponential.
        :param nbfunc: The function to use in decreasing the neighborhood size.
        The functions are defined in utils. Default is exponential.
        :param alpha: a float value, specifying how much weight the
        input value receives in the BMU calculation.
        :param beta: a float value, specifying how much weight the context
        receives in the BMU calculation.
        :param sigma: The starting value for the neighborhood size, which is
        decreased over time. If sigma is None (default), sigma is calculated as
        ((max(map_dim) / 2) + 0.01), which is generally a good value.
        """
        influence_size = reduce(np.multiply, map_dim)

        super().__init__(map_dim,
                         data_dim,
                         learning_rate,
                         lrfunc,
                         nbfunc,
                         sigma,
                         min_max=np_max,
                         influence_size=influence_size)

        self.context_weights = np.zeros((self.weight_dim, self.weight_dim), dtype=np.float32)
        self.alpha = alpha
        self.beta = beta

    def _example(self, x, x_n, influences, **kwargs):
        """
        A single example.

        :param X: a numpy array of data
        :param influences: The influence at the current epoch,
        given the learning rate and map size
        :return: A vector describing activation values for each unit.
        """

        prev = kwargs['prev_activation']

        activation = self.forward(x, x_n, prev_activation=prev)
        self.backward(x, influences, activation, previous_activation=prev)

        return activation

    def backward(self, x, influences, activation, **kwargs):
        """
        Backward pass through the network, including update.

        :param x: The input data
        :param influences: The influences at the current time-step
        :param activation: The activation at the output
        :param kwargs:
        :return: None
        """

        prev = kwargs['previous_activation']
        influence = self._apply_influences(activation, influences)
        # Update
        self.weights += np.mean(self._calculate_update(x, self.weights, influence[:, :, :self.data_dim]), 0)
        res = np.squeeze(np.mean(self._calculate_update(prev, self.context_weights, influence), 0))
        self.context_weights += res

    def forward(self, x, x_n, **kwargs):
        """
        Get the best matching units, based on euclidean distance.

        The euclidean distance between the context vector and context weights
        and input vector and weights are used to estimate the BMU. The
        activation of the units is the sum of the distances, weighed by two
        constants, alpha and beta.

        The exponent of the negative of this value describes the activation
        of the units. This function is bounded between 0 and 1, where 1 means
        the unit matches well and 0 means the unit doesn't match at all.

        :param x: A batch of data.
        :return: The activation, and difference between the input and weights.
        """
        prev = kwargs['prev_activation']
        # Differences is the components of the weights subtracted from
        # the weight vector.
        distance_x = self.distance_function(x, x_n, self.weights)
        prev_n = np.sum(np.square(prev), axis=1)
        distance_y = self.distance_function(prev, prev_n, self.context_weights)

        activation = np.exp(-(np.multiply(distance_x, self.alpha) + np.multiply(distance_y, self.beta)))

        return activation

    @classmethod
    def load(cls, path):
        """
        Load a recursive SOM from a JSON file.

        You can use this function to load weights of other SOMs.
        If there are no context weights, the context weights will be set to 0.

        :param path: The path to the JSON file.
        :return: A RecSOM.
        """
        data = json.load(open(path))

        weights = data['weights']
        weights = np.asarray(weights, dtype=np.float32)
        datadim = weights.shape[1]

        dimensions = data['dimensions']
        lrfunc = expo if data['lrfunc'] == 'expo' else linear
        nbfunc = expo if data['nbfunc'] == 'expo' else linear
        lr = data['lr']
        sigma = data['sigma']

        try:
            context_weights = data['context_weights']
            context_weights = np.asarray(context_weights, dtype=np.float32)
        except KeyError:
            context_weights = np.zeros((len(weights), len(weights)))

        try:
            alpha = data['alpha']
            beta = data['beta']
        except KeyError:
            alpha = 3.0
            beta = 1.0

        s = cls(dimensions,
                datadim,
                lr,
                lrfunc=lrfunc,
                nbfunc=nbfunc,
                sigma=sigma,
                alpha=alpha,
                beta=beta)

        s.weights = weights
        s.context_weights = context_weights
        s.trained = True

        return s

    def save(self, path):
        """
        Save a SOM to a JSON file.

        :param path: The path to the JSON file that will be created
        :return: None
        """
        dicto = {}
        dicto['weights'] = [[float(w) for w in x] for x in self.weights]
        dicto['context_weights'] = [[float(w) for w in x] for x in self.context_weights]
        dicto['dimensions'] = self.map_dimensions
        dicto['lrfunc'] = 'expo' if self.lrfunc == expo else 'linear'
        dicto['nbfunc'] = 'expo' if self.nbfunc == expo else 'linear'
        dicto['lr'] = self.learning_rate
        dicto['sigma'] = self.sigma
        dicto['alpha'] = self.alpha
        dicto['beta'] = self.beta

        json.dump(dicto, open(path, 'w'))


class Merging(Sequential):

    def __init__(self,
                 map_dim,
                 data_dim,
                 learning_rate,
                 alpha,
                 beta,
                 sigma=None,
                 lrfunc=expo,
                 nbfunc=expo,
                 min_max=np_min):
        """
        A merging som.

        :param map_dim: A tuple of map dimensions,
        e.g. (10, 10) instantiates a 10 by 10 map.
        :param data_dim: The data dimensionality.
        :param learning_rate: The learning rate, which is decreased
        according to some function.
        :param lrfunc: The function to use in decreasing the learning rate.
        The functions are defined in utils. Default is exponential.
        :param nbfunc: The function to use in decreasing the neighborhood size.
        The functions are defined in utils. Default is exponential.
        :param alpha: Controls the rate of context dependence, where 0 is low
        context dependence, and 1 is high context dependence. Should start at
        low values (e.g. 0.0 to 0.05)
        :param beta: A float between 1 and 0 specifying the influence of
        context on previous weights. Static, usually 0.5.
        :param sigma: The starting value for the neighborhood size, which is
        decreased over time. If sigma is None (default), sigma is calculated as
        ((max(map_dim) / 2) + 0.01), which is generally a good value.
        """
        super().__init__(map_dim,
                         data_dim,
                         learning_rate,
                         lrfunc,
                         nbfunc,
                         sigma,
                         min_max)

        self.alpha = alpha
        self.beta = beta
        self.context_weights = np.ones_like(self.weights)
        self.entropy = 0

    def _example(self, x, x_n, influences, **kwargs):
        """
        A single example.

        :param X: a numpy array of data
        :param influences: The influence at the current epoch,
        given the learning rate and map size
        :return: A vector describing activation values for each unit.
        """
        prev = kwargs['prev_activation']

        # Get the indices of the Best Matching Units, given the data.
        activation = self.forward(x, x_n, prev_activation=prev)
        self.backward(x, influences, activation, prev_activation=prev)

        return activation

    def backward(self, x, influences, activation, **kwargs):
        """
        Backward pass through the network, including update.

        :param x: The input data
        :param influences: The influences at the current time-step
        :param activation: The activation at the output
        :param kwargs:
        :return: None
        """

        prev_bmu = self.min_max(kwargs['prev_activation'], 1)[1]
        context = (1 - self.beta) * self.weights[prev_bmu] + self.beta * self.context_weights[prev_bmu]

        influence = self._apply_influences(activation, influences)
        self.weights += np.mean(self._calculate_update(x, self.weights, influence), 0)
        self.context_weights += np.mean(self._calculate_update(context, self.context_weights, influence), 0)

    def _entropy(self, prev_bmus, prev_update):
        """
        Calculate the entropy activation pattern.

        Merging SOMS perform better when their weight-based activation profile
        has high entropy, as small changes in context will then be able to have
        a larger effect.

        This is reflected in this function, which increases the importance of
        context by decreasing alpha if the entropy decreases. The function uses
        a very large momentum term of 0.9 to make sure the entropy does not
        rise or fall too sharply.

        :param prev_bmus: The previous BMUs.
        :param prev_update: The previous update, used as a momentum term.
        :return:
        """
        prev_bmus = np.array(list(prev_bmus.values()), dtype=np.float32)
        prev_bmus = prev_bmus / np.sum(prev_bmus)

        new_entropy = -np.sum(prev_bmus * np.nan_to_num(np.log2(prev_bmus)))
        entropy_diff = (new_entropy - self.entropy)

        update = (entropy_diff * 0.1) + (prev_update * 0.9)

        self.entropy = new_entropy

        logger.info("Entropy: {0}".format(new_entropy))

        return update

    def forward(self, x, x_n, **kwargs):
        """
        Get the best matching units, based on euclidean distance.

        :param x: The input vector
        :return: An integer, representing the index of the best matching unit.
        """
        # Differences is the components of the weights
        # subtracted from the weight vector.

        prev_bmu = self.min_max(kwargs['prev_activation'], 1)[1]
        context = (1 - self.beta) * self.weights[prev_bmu] + self.beta * self.context_weights[prev_bmu]

        distances_x = self.distance_function(x,
                                             x_n,
                                             self.weights)

        context_n = np.sum(np.square(context), axis=1)
        distances_y = self.distance_function(context,
                                             context_n,
                                             self.context_weights)

        # BMU is based on a weighted addition of current and
        # previous activation.
        activations = np.multiply(distances_x, 1 - self.alpha) + np.multiply(distances_y, self.alpha)

        return activations

    def _predict_base(self, X):
        """
        Predict distances to some input data.

        :param X: The input data.
        :return: An array of arrays, representing the activation
        each node has to each input.
        """

        X, X_norm = self._create_batches(X, len(X))
        distances = []

        prev_activation = self._init_prev(X)

        for x, x_n in zip(X, X_norm):
            prev_activation = self.weights[self.min_max(prev_activation, 1)[1]]
            prev_activation = self.forward(x, x_n, prev_activation=prev_activation)
            distances.extend(prev_activation)

        return np.array(distances, dtype=np.float32)

    @classmethod
    def load(cls, path):
        """
        Loads a SOM from a JSON file.

        A normal SOM can be loaded via this method. Any attributes not present
        in the loaded JSON will be initialized to sane values.

        :param path: The path to the JSON file.
        :return: A trained mergeSom.
        """

        data = json.load(open(path))

        weights = data['weights']
        weights = np.array(weights, dtype=np.float32)

        datadim = weights.shape[1]
        dimensions = data['dimensions']

        lrfunc = expo if data['lrfunc'] == 'expo' else linear
        nbfunc = expo if data['nbfunc'] == 'expo' else linear
        lr = data['lr']
        sigma = data['sigma']

        try:
            context_weights = data['context_weights']
            context_weights = np.array(context_weights, dtype=np.float32)
        except KeyError:
            context_weights = np.ones(weights.shape)

        try:
            alpha = data['alpha']
            beta = data['beta']
            entropy = data['entropy']
        except KeyError:
            alpha = 0.0
            beta = 0.5
            entropy = 0.0

        s = cls(dimensions, datadim, lr, lrfunc=lrfunc, nbfunc=nbfunc, sigma=sigma, alpha=alpha, beta=beta)
        s.entropy = entropy
        s.weights = weights
        s.context_weights = context_weights
        s.trained = True

        return s

    def save(self, path):
        """
        Saves the merging SOM to a JSON file.

        :param path: The path to which to save the JSON file.
        :return: None
        """

        to_save = {}
        to_save['weights'] = [[float(w) for w in x] for x in self.weights]
        to_save['context_weights'] = [[float(w) for w in x] for x in self.context_weights]
        to_save['dimensions'] = self.map_dimensions
        to_save['lrfunc'] = 'expo' if self.lrfunc == expo else 'linear'
        to_save['nbfunc'] = 'expo' if self.nbfunc == expo else 'linear'
        to_save['lr'] = self.learning_rate
        to_save['sigma'] = self.sigma
        to_save['alpha'] = self.alpha
        to_save['beta'] = self.beta
        to_save['entropy'] = self.entropy

        json.dump(to_save, open(path, 'w'))
