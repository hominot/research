import tensorflow as tf

from util.registry.data_loader import DataLoader
from util.dataset import split_train_test_by_label
from util.dataset import create_dataset_from_directory
from util.registry.model import Model
from util.registry.metric import Metric
from util.tensorflow import set_tensorboard_writer


tf.enable_eager_execution()


conf = {
    'dataset': {
        'name': 'mnist',
        'train': {
            'data_directory': '/tmp/research/experiment/mnist/train',
            'batch_size': 64,
            'group_size': 2,
            'num_groups': 8,
            'min_class_size': 8,
        },
        'test': {
            'data_directory': '/tmp/research/experiment/mnist/test',
            'num_negative_examples': 1,
        },
    },
    'model': {
        'name': 'simple_dense',
        'k': 4,
        'loss': {
            'name': 'npair',
            'n': 4
        }
    },
    'metrics': [
        {
            'name': 'accuracy',
            'compute_period': 10,
            'conf': {
                'sampling_rate': 0.1,
            }
        },
    ]
}

writer = set_tensorboard_writer(conf)
writer.set_as_default()

data_loader: DataLoader = DataLoader.create(conf['dataset'])
if conf['dataset']['train']['data_directory'] and conf['dataset']['test']['data_directory']:
    training_files, training_labels = create_dataset_from_directory(
        conf['dataset']['train']['data_directory']
    )
    testing_files, testing_labels = create_dataset_from_directory(
        conf['dataset']['test']['data_directory']
    )
else:
    image_files, labels = data_loader.load_image_files()
    training_data, testing_data = split_train_test_by_label(image_files, labels)
    training_files, training_labels = zip(*training_data)
    testing_files, ttesting_labels = zip(*testing_data)

extra_info = {
    'num_labels': max(training_labels),
}

test_ds = data_loader.create_verification_test_dataset(testing_files, testing_labels).batch(256)

step_counter = tf.train.get_or_create_global_step()
optimizer = tf.train.AdamOptimizer(learning_rate=0.0001)
model = Model.create(conf['model'], extra_info)

device = '/gpu:0' if tf.test.is_gpu_available() else '/cpu:0'

for _ in range(10):
    train_ds = data_loader.create_grouped_dataset(
        training_files, training_labels,
        group_size=conf['dataset']['train']['group_size'],
        num_groups=conf['dataset']['train']['num_groups'],
        min_class_size=conf['dataset']['train']['min_class_size'],
    ).batch(conf['dataset']['train']['batch_size'])
    with tf.device(device):
        for (batch, (images, labels)) in enumerate(train_ds):
            with tf.contrib.summary.record_summaries_every_n_global_steps(
                    10, global_step=step_counter):
                with tf.GradientTape() as tape:
                    loss_value = model.loss(images, labels)
                    tf.contrib.summary.scalar('loss', loss_value)

                for metric_conf in conf['metrics']:
                    if int(tf.train.get_global_step()) % metric_conf.get('compute_period', 10) == 0:
                        metric = Metric.create(metric_conf)
                        score = metric.compute_metric(model, test_ds, **metric_conf['conf'])
                        if type(score) is dict:
                            for metric, s in score.items():
                                tf.contrib.summary.scalar(metric, s)
                        else:
                            tf.contrib.summary.scalar(metric_conf['name'], score)
                grads = tape.gradient(loss_value, model.variables)
                optimizer.apply_gradients(
                    zip(grads, model.variables), global_step=step_counter)
