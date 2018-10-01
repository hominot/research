from util.dataset import download, extract_zip
from util.registry.data_loader import DataLoader
from shutil import copyfile

import tensorflow as tf
import os


class StanfordOnlineProductDataLoader(DataLoader):
    name = 'stanford_online_product'

    def prepare_files(self):
        data_directory = os.path.join(self.data_directory, self.name)
        if tf.gfile.Exists(data_directory):
            count = 0
            for root, dirnames, filenames in os.walk(data_directory):
                for filename in filenames:
                    if filename.lower().endswith('.jpg'):
                        count += 1
            if count == 120053:
                return
        filepath = download(
            'https://s3-us-west-2.amazonaws.com/hominot/research/dataset/Stanford_Online_Products.zip',
            os.path.join(self.temp_directory, self.name)
        )
        extract_zip(filepath, os.path.join(self.temp_directory, self.name))
        extracted_path = os.path.join(self.temp_directory, self.name, 'Stanford_Online_Products')
        for directory in next(os.walk(extracted_path))[1]:
            for filename in os.listdir(os.path.join(extracted_path, directory)):
                object_id, index = filename.split('.')[0].split('_')
                if not tf.gfile.Exists(os.path.join(data_directory, object_id)):
                    tf.gfile.MakeDirs(os.path.join(data_directory, object_id))
                copyfile(os.path.join(extracted_path, directory, filename), os.path.join(data_directory, object_id, filename))

    def _image_parse_function(self, filename):
        width = self.conf['image']['width']
        height = self.conf['image']['height']
        channel = self.conf['image']['channel']
        image_string = tf.read_file(filename)
        image_decoded = tf.image.decode_jpeg(image_string, channels=channel)
        image_resized = tf.image.resize_image_with_pad(image_decoded, target_height=height, target_width=width)
        image_normalized = (image_resized / 255. - 0.5) * 2
        image_normalized = tf.reshape(image_normalized, [width, height, channel])
        return image_normalized


if __name__ == '__main__':
    data_loader = DataLoader.create('stanford_online_product')
    data_loader.prepare_files()
