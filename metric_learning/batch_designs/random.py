from util.registry.batch_design import BatchDesign

import tensorflow as tf
import random


class RandomBatchDesign(BatchDesign):
    name = 'random'

    def create_dataset(self, image_files, labels, testing=False):
        data = list(zip(image_files, labels, range(len(image_files))))
        random.shuffle(data)
        image_files, labels, image_ids = zip(*data)
        images_ds = tf.data.Dataset.from_tensor_slices(
            tf.constant(image_files)
        ).map(self.data_loader.image_parse_function)
        if 'random_flip' in self.conf['image'] and self.conf['image']['random_flip']:
            images_ds = images_ds.map(self.data_loader.random_flip)
        if 'random_crop' in self.conf['image']:
            images_ds = images_ds.map(self.data_loader.random_crop)
        labels_ds = tf.data.Dataset.from_tensor_slices(tf.constant(labels))
        image_ids_ds = tf.data.Dataset.from_tensor_slices(tf.constant(image_ids))

        return tf.data.Dataset.zip((images_ds, labels_ds, image_ids_ds)), len(data)

    def get_pairwise_distances(self, batch, model, distance_function):
        raise NotImplementedError

    def get_npair_distances(self, batch, model, distance_function):
        raise NotImplementedError

    def get_embeddings(self, batch, model, distance_function):
        raise NotImplementedError