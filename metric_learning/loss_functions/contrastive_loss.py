import tensorflow as tf
import numpy as np
import random

from collections import defaultdict


def sample_pairs(images, labels, num_positives, num_negatives):
    data_map = defaultdict(list)
    positive_pair_candidates = []
    for image, label in zip(images, labels):
        data_map[int(label)].append(image)
    for label, image_list in data_map.items():
        if len(image_list) >= 2:
            positive_pair_candidates.append(label)

    images_1 = []
    images_2 = []
    pair_labels = []

    if positive_pair_candidates:
        for _ in range(num_positives):
            label = random.choice(positive_pair_candidates)
            x, y = random.sample(data_map[label], 2)
            images_1.append(x)
            images_2.append(y)
            pair_labels.append(1)

    if len(data_map.keys()) >= 2:
        for _ in range(num_negatives):
            x, y = random.sample(data_map.keys(), 2)
            images_1.append(random.choice(data_map[x]))
            images_2.append(random.choice(data_map[y]))
            pair_labels.append(0)
    images_1 = tf.stack(images_1)
    images_2 = tf.stack(images_2)
    pair_labels = pair_labels
    return images_1, images_2, pair_labels


def contrastive_loss(embeddings, labels):
    images_1, images_2, pair_labels = sample_pairs(
        embeddings, labels, labels.shape[0], labels.shape[0])

    pair_labels = np.array(pair_labels)

    positive_images_1 = tf.boolean_mask(images_1, pair_labels == 1)
    positive_images_2 = tf.boolean_mask(images_2, pair_labels == 1)
    negative_images_1 = tf.boolean_mask(images_1, pair_labels == 0)
    negative_images_2 = tf.boolean_mask(images_2, pair_labels == 0)

    d_p = tf.reduce_sum(tf.square(positive_images_1 - positive_images_2), axis=1)
    d_n = tf.reduce_sum(tf.square(negative_images_1 - negative_images_2), axis=1)
    loss_value = sum(d_p) + sum(tf.maximum(0, 1 - d_n))

    return loss_value
