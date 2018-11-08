from util.registry.metric import Metric

from collections import defaultdict
from tqdm import tqdm
from util.tensor_operations import compute_pairwise_distances
from util.tensor_operations import pairwise_matching_matrix
from util.tensor_operations import stable_sqrt
from util.tensor_operations import upper_triangular_part
from metric_learning.constants.distance_function import DistanceFunction

import tensorflow as tf


def count_singletons(all_labels):
    counts = defaultdict(int)
    for label in all_labels:
        counts[label] += 1
    return len(list(filter(lambda x: x == 1, counts.values())))


def compute_contrastive_loss(conf, embeddings_list, labels_list):
    data = zip(embeddings_list, labels_list)
    batches = tqdm(data, total=len(embeddings_list), desc='contrastive', dynamic_ncols=True)
    loss = 0.0
    num_pairs = 0
    for i, (embeddings, labels) in enumerate(batches):
        for j, (test_embeddings, test_labels) in enumerate(data):
            if i > j:
                continue
            distances = compute_pairwise_distances(
                embeddings, test_embeddings, DistanceFunction.EUCLIDEAN_DISTANCE_SQUARED)
            matches = pairwise_matching_matrix(labels, test_labels)
            if i == j:
                distances = upper_triangular_part(distances)
                matches = upper_triangular_part(matches)
                positive_distances = tf.boolean_mask(distances, matches)
                negative_distances = tf.boolean_mask(distances, ~matches)
            else:
                positive_distances = tf.boolean_mask(distances, matches)
                negative_distances = tf.boolean_mask(distances, ~matches)
            loss_value = (
                sum(positive_distances) +
                sum(tf.square(tf.maximum(0, conf['loss']['alpha'] - stable_sqrt(negative_distances))))
            )
            loss += float(loss_value)
            num_pairs += int(positive_distances.shape[0]) + int(negative_distances.shape[0])
    return loss / num_pairs


class ContrastiveLoss(Metric):
    name = 'contrastive_loss'

    def compute_metric(self, model, ds, num_testcases):
        embeddings_list, labels_list = self.get_embeddings(
            model, ds, num_testcases)

        return compute_contrastive_loss(self.conf, embeddings_list, labels_list)