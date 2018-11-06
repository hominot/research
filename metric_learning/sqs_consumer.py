import tensorflow as tf

import boto3
import json
import os
import sys
import time

from util.train import train

conn_sqs = boto3.resource('sqs')

if __name__ == '__main__':
    tf.enable_eager_execution()
    queue = conn_sqs.get_queue_by_name(QueueName='experiment-configs')
    messages = queue.receive_messages(
        MaxNumberOfMessages=1,
        WaitTimeSeconds=0)

    for message in messages:
        conf = json.loads(message.body)
        message.delete()
        train(conf, None)

    time.sleep(10)
    os.execv(__file__, sys.argv)
