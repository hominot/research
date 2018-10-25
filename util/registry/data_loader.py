from util.registry.class_registry import ClassRegistry
from util.dataset import load_images_from_directory
from util.config import CONFIG

import os
import tensorflow as tf


class DataLoader(object, metaclass=ClassRegistry):
    module_path = 'metric_learning.data_loaders'

    def __init__(self, conf, extra_info):
        super(DataLoader, self).__init__()
        self.conf = conf
        self.extra_info = extra_info

    def prepare_files(self):
        raise NotImplementedError

    def image_parse_function(self, filename):
        raise NotImplementedError

    def random_crop(self, image):
        width = self.conf['image']['random_crop']['width']
        height = self.conf['image']['random_crop']['height']
        channel = self.conf['image']['channel']
        return tf.random_crop(image, [width, height, channel])

    def random_flip(self, image):
        return tf.image.random_flip_left_right(image)

    def _center_crop(self, image):
        crop_width = self.conf['image']['random_crop']['width']
        crop_height = self.conf['image']['random_crop']['height']
        width = self.conf['image']['width']
        height = self.conf['image']['height']
        return tf.image.crop_to_bounding_box(
            image,
            (width - crop_width) // 2,
            (height - crop_height) // 2,
            crop_width,
            crop_height)

    def _parse_and_augment(self, dataset: tf.data.Dataset):
        dataset = dataset.map(self.image_parse_function)
        if 'random_crop' in self.conf['image']:
            dataset = dataset.flat_map(self.random_crop)
        return dataset

    def _parse_and_center(self, dataset: tf.data.Dataset):
        dataset = dataset.map(self.image_parse_function)
        if 'random_crop' in self.conf['image']:
            dataset = dataset.map(self._center_crop)
        return dataset

    def load_image_files(self):
        self.prepare_files()
        image_files, labels = load_images_from_directory(
            os.path.join(CONFIG['dataset']['data_dir'], self.name))
        return image_files, labels

    def __str__(self):
        return self.conf['dataset']['name']
