from util.registry.batch_design import BatchDesign

from collections import defaultdict
from util.tensor_operations import pairwise_matching_matrix
from util.tensor_operations import upper_triangular_part
from util.tensor_operations import get_n_blocks
from util.tensor_operations import pairwise_product
from util.tensor_operations import compute_pairwise_distances
from util.tensor_operations import repeat_columns

import numpy as np
import tensorflow as tf
import random


def get_npair_distances(embeddings, n, distance_function, transpose=False):
    num_groups = int(embeddings.shape[0]) // 2
    evens = tf.range(num_groups, dtype=tf.int64) * 2
    odds = tf.range(num_groups, dtype=tf.int64) * 2 + 1
    even_embeddings = tf.gather(embeddings, evens)
    odd_embeddings = tf.gather(embeddings, odds)

    pairwise_distances = compute_pairwise_distances(
        even_embeddings, odd_embeddings, distance_function)

    return (
        get_n_blocks(pairwise_distances, n, transpose=transpose),
        get_n_blocks(
            tf.cast(tf.eye(num_groups), tf.bool), n, transpose=transpose)
    )


class GroupedBatchDesign(BatchDesign):
    name = 'grouped'

    def get_next_batch(self, image_files, labels, batch_conf):
        data = list(zip(image_files, labels))
        random.shuffle(data)

        batch_size = batch_conf['batch_size']
        group_size = batch_conf['group_size']
        num_groups = batch_size // group_size
        data_map = defaultdict(list)
        for image_file, label in data:
            data_map[label].append(image_file)

        data_map = dict(filter(lambda x: len(x[1]) >= group_size, data_map.items()))
        sampled_labels = np.random.choice(
            list(data_map.keys()), size=num_groups, replace=False)
        grouped_data = []
        for label in sampled_labels:
            for _ in range(group_size):
                image_file = data_map[label].pop()
                grouped_data.append((image_file, label))
        return grouped_data

    def get_pairwise_distances(self, batch, model, distance_function, training=True):
        images, labels = batch
        embeddings = model(images, training=training)

        if self.conf['batch_design'].get('npair'):
            pairwise_distances, matching_labels_matrix = get_npair_distances(
                embeddings, self.conf['batch_design']['npair'], distance_function)
            weights = self.get_npair_pairwise_weights(
                labels, self.conf['batch_design']['npair'], model.extra_info)
            return (
                tf.reshape(pairwise_distances, [-1]),
                tf.reshape(matching_labels_matrix, [-1]),
                tf.reshape(1 / weights, [-1]),
            )
        else:
            group_size = self.conf['batch_design']['group_size']
            pairwise_distances = compute_pairwise_distances(
                embeddings, embeddings, distance_function)
            matching_labels_matrix = pairwise_matching_matrix(labels, labels)
            weights = self.get_pairwise_weights(labels, group_size, model.extra_info)
            return (
                upper_triangular_part(pairwise_distances),
                upper_triangular_part(matching_labels_matrix),
                upper_triangular_part(1 / weights),
            )

    @staticmethod
    def get_npair_pairwise_weights(labels, npair, extra_info):
        batch_size = int(labels.shape[0])
        group_size = 2
        num_groups = batch_size // group_size
        num_labels = extra_info['num_labels']
        evens = tf.range(num_groups, dtype=tf.int64) * 2
        even_labels = tf.gather(labels, evens)
        num_average_images_per_label = extra_info['num_images'] / extra_info['num_labels']
        label_counts = tf.gather(
            tf.constant(extra_info['label_counts'], dtype=tf.float32),
            even_labels) / num_average_images_per_label
        label_counts_multiplied = get_n_blocks(
            pairwise_product(label_counts, label_counts),
            npair)
        positive_label_counts = label_counts[:, None]
        negative_weights = (npair - 1) / (num_labels - 1) / label_counts_multiplied
        positive_weights = 1 / positive_label_counts / (positive_label_counts - 1 / num_average_images_per_label)
        matching_labels_matrix = get_n_blocks(tf.cast(tf.eye(num_groups), tf.bool), npair)
        weights = positive_weights * tf.cast(matching_labels_matrix, tf.float32) + negative_weights * tf.cast(~matching_labels_matrix, tf.float32)
        return weights

    @staticmethod
    def get_npair_weights(labels, npair, extra_info):
        batch_size = int(labels.shape[0])
        group_size = 2
        num_groups = batch_size // group_size
        evens = tf.range(num_groups, dtype=tf.int64) * 2
        even_labels = tf.gather(labels, evens)
        num_average_images_per_label = extra_info['num_images'] / extra_info['num_labels']
        label_counts = tf.gather(
            tf.constant(extra_info['label_counts'], dtype=tf.float32),
            even_labels) / num_average_images_per_label
        weights = 1 / tf.reduce_prod(
            get_n_blocks(tf.transpose(repeat_columns(label_counts)), npair),
            axis=1
        ) / (label_counts - 1 / num_average_images_per_label)
        return weights

    @staticmethod
    def get_pairwise_weights(labels, group_size, extra_info):
        batch_size = int(labels.shape[0])
        num_groups = batch_size // group_size
        num_average_images_per_label = extra_info['num_images'] / extra_info['num_labels']
        label_counts = tf.gather(
            tf.constant(extra_info['label_counts'], dtype=tf.float32),
            labels) / num_average_images_per_label
        positive_label_counts = label_counts
        matching_labels_matrix = pairwise_matching_matrix(labels, labels)
        label_counts_multiplied = pairwise_product(label_counts, label_counts)

        num_labels = extra_info['num_labels']
        negative_weights = (num_groups - 1) * group_size / (num_labels - 1) / label_counts_multiplied
        positive_weights = (group_size - 1) / positive_label_counts / (positive_label_counts - 1 / num_average_images_per_label)
        weights = positive_weights * tf.cast(matching_labels_matrix, tf.float32) + negative_weights * tf.cast(~matching_labels_matrix, tf.float32)
        return weights

    def get_npair_distances(self, batch, model, n, distance_function, training=True):
        if self.conf['batch_design']['group_size'] != 2:
            raise Exception('group size must be 2 in order to get npair distances')
        if (self.conf['batch_design']['batch_size'] // 2) % n != 0:
            raise Exception(
                'n does not divide the number of groups: n={}, num_groups={}'.format(
                    n, self.conf['batch_size'] // 2
                ))

        images, labels = batch
        embeddings = model(images, training=training)

        return get_npair_distances(embeddings, n, distance_function)

    def get_embeddings(self, batch, model, distance_function, training=True):
        images, _ = batch
        return model(images, training=training)
