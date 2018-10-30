import tensorflow as tf

import argparse
import copy
import math
import os

from tqdm import tqdm
from util.dataset import create_test_dataset
from util.dataset import get_training_files_labels
from util.registry.data_loader import DataLoader
from util.registry.batch_design import BatchDesign
from util.registry.model import Model
from util.registry.metric import Metric
from util.logging import set_tensorboard_writer
from util.logging import upload_tensorboard_log_to_s3
from util.logging import create_checkpoint
from util.logging import save_config
from metric_learning.example_configurations import configs
from util.config import CONFIG
from util.config import generate_configs_from_experiment


def evaluate(model, test_dataset, num_testcases):
    with tf.contrib.summary.always_record_summaries():
        for metric_conf in model.conf['metrics']:
            metric = Metric.create(metric_conf['name'], conf)
            score = metric.compute_metric(model, test_dataset, num_testcases)
            if type(score) is dict:
                for metric, s in score.items():
                    tf.contrib.summary.scalar('test ' + metric, s)
                    print('{}: {}'.format(metric, s))
            else:
                tf.contrib.summary.scalar('{}'.format(metric_conf['name']), score)
                print('{}: {}'.format(metric_conf['name'], score))


def compute_all_embeddings(model, conf, training_files):
    data_loader = DataLoader.create(conf['dataset']['name'], conf)
    ds = BatchDesign.create('vanilla', conf, {'data_loader': data_loader})
    train_ds, num_examples = ds.create_dataset(
        training_files, [0] * len(training_files), testing=True)
    train_ds = train_ds.batch(48)
    batches = tqdm(train_ds,
                   total=math.ceil(num_examples / 48),
                   desc='drift')
    embeddings = []
    for (batch, (images, labels, image_ids)) in enumerate(batches):
        embeddings.append(model(images, training=False))
    return embeddings


def train(conf):
    data_loader = DataLoader.create(conf['dataset']['name'], conf)
    training_files, training_labels = get_training_files_labels(conf)
    if conf['dataset']['cross_validation_split'] != -1:
        validation_dir = os.path.join(CONFIG['dataset']['experiment_dir'],
                                      conf['dataset']['name'],
                                      'train',
                                      str(conf['dataset']['cross_validation_split']))
        test_dataset, test_num_testcases = create_test_dataset(
            conf, data_loader, validation_dir)
    else:
        test_dir = os.path.join(CONFIG['dataset']['experiment_dir'],
                                conf['dataset']['name'],
                                'test')
        test_dataset, test_num_testcases = create_test_dataset(
            conf, data_loader, test_dir)

    writer, run_name = set_tensorboard_writer(conf)
    writer.set_as_default()
    save_config(conf, run_name)

    dataset = BatchDesign.create(
        conf['batch_design']['name'], conf, {'data_loader': data_loader})

    extra_info = {
        'num_labels': max(training_labels) + 1,
        'num_images': len(training_files),
    }
    model = Model.create(conf['model']['name'], conf, extra_info)
    optimizers = {
        k: tf.train.GradientDescentOptimizer(learning_rate=v) for
        k, (v, _) in model.learning_rates().items()
    }
    checkpoint = tf.train.Checkpoint(model=model)

    batch_design_conf = conf['batch_design']
    if CONFIG['train'].getboolean('initial_evaluation'):
        evaluate(model, test_dataset, test_num_testcases)
    step_counter = tf.train.get_or_create_global_step()

    initial_embeddings = None
    embeddings = None
    if CONFIG['train'].getboolean('compute_drift'):
        embeddings = compute_all_embeddings(model, conf, training_files)
        initial_embeddings = embeddings
    total_drift = 0.0
    for epoch in range(conf['trainer']['num_epochs']):
        train_ds, num_examples = dataset.create_dataset(training_files, training_labels)
        train_ds = train_ds.batch(batch_design_conf['batch_size'], drop_remainder=True)
        batches = tqdm(train_ds,
                       total=math.ceil(num_examples / batch_design_conf['batch_size']),
                       desc='epoch #{}'.format(epoch + 1))
        for batch in batches:
            with tf.contrib.summary.record_summaries_every_n_global_steps(
                    10, global_step=step_counter):
                with tf.GradientTape() as tape:
                    loss_value = model.loss(batch, model, dataset)
                    batches.set_postfix({'loss': float(loss_value)})
                    tf.contrib.summary.scalar('loss', loss_value)

                grads = tape.gradient(loss_value, model.variables)
                for optimizer_key, (_, variables) in model.learning_rates().items():
                    filtered_grads = filter(lambda x: x[1] in variables, zip(grads, model.variables))
                    optimizers[optimizer_key].apply_gradients(filtered_grads)
                step_counter.assign_add(1)
                if CONFIG['tensorboard'].getboolean('s3_upload') and int(step_counter) % int(CONFIG['tensorboard']['s3_upload_period']) == 0:
                    upload_tensorboard_log_to_s3(run_name)
        if CONFIG['train'].getboolean('compute_drift'):
            embeddings_after = compute_all_embeddings(model, conf, training_files)
            avg_drift = sum([
                tf.reduce_sum(tf.norm(before - after, axis=1))
                for before, after in zip(embeddings, embeddings_after)
            ]) / len(training_files)
            final_drift = sum([
                tf.reduce_sum(tf.norm(before - after, axis=1))
                for before, after in zip(embeddings_after, initial_embeddings)
            ]) / len(training_files)
            total_drift += avg_drift
            with tf.contrib.summary.always_record_summaries():
                tf.contrib.summary.scalar('avg_drift', avg_drift)
                tf.contrib.summary.scalar('total_drift', total_drift)
                tf.contrib.summary.scalar('drift_ratio', final_drift / total_drift)
            print('Drift avg: {:4f}, Total drift: {:4f}, Drift ratio: {:4f}'.format(
                float(avg_drift), float(total_drift), float(final_drift / total_drift)
            ))
            embeddings = embeddings_after
        print('epoch #{} checkpoint: {}'.format(epoch + 1, run_name))
        if CONFIG['tensorboard'].getboolean('enable_checkpoint'):
            create_checkpoint(checkpoint, run_name)
        evaluate(model, test_dataset, test_num_testcases)


if __name__ == '__main__':
    tf.enable_eager_execution()

    parser = argparse.ArgumentParser(description='Train using a specified config')
    parser.add_argument('--config', help='config to run')
    parser.add_argument('--experiment', help='experiment to run')
    parser.add_argument('--experiment_index',
                        help='index of the experiment to run',
                        type=int)
    parser.add_argument('--split',
                        help='cross validation split number to use as validation data',
                        default=None,
                        type=int)
    args = parser.parse_args()

    if args.experiment:
        experiments = generate_configs_from_experiment(args.experiment)
        conf = copy.deepcopy(experiments[args.experiment_index])
        if args.split is not None:
            conf['dataset']['cross_validation_split'] = args.split
        train(conf)
    else:
        conf = copy.deepcopy(configs[args.config])
        if args.split is not None:
            conf['dataset']['cross_validation_split'] = args.split
        train(conf)
