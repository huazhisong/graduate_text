# -*- coding:utf-8 -*-
import tensorflow as tf
import os
import numpy as np
import datetime
import data_utls
from models import Model
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

# Parameters
# ==================================================

# Data loading params
tf.flags.DEFINE_string(
    "data_dir",
    "../data/data_by_ocean/",
    "direction for data")
tf.flags.DEFINE_string("checkpointDir", "./logs/", "log dir")

# Model Hyperparameters
tf.flags.DEFINE_integer("embedding_dim", 300,
                        "Dimensionality of character embedding (default: 128)")
tf.flags.DEFINE_string("filter_sizes", "3",
                       "Comma-separated filter sizes (default: '3,4,5')")
tf.flags.DEFINE_integer(
    "num_filters", 100, "Number of filters per filter size (default: 128)")
tf.flags.DEFINE_integer(
    "n_hidden", 300, "Size of hidden cell (default: 300)")
tf.flags.DEFINE_float("dropout_keep_prob", 0.5,
                      "Dropout keep probability (default: 0.5)")
tf.flags.DEFINE_float("l2_reg_lambda", 0.0,
                      "L2 regularization lambda (default: 0.0)")
tf.flags.DEFINE_float("learning_rate", 1e-4, "learning rate")
tf.flags.DEFINE_float("decay_rate", 0.96, "decay rate")

# Training parameters
tf.flags.DEFINE_integer("batch_size", 100, "Batch Size (default: 64)")
tf.flags.DEFINE_integer(
    "num_epochs", 200, "Number of training epochs (default: 200)")
tf.flags.DEFINE_integer(
    "require_improvement", 10,
    "Require improvement steps for training data (default: 10)")
tf.flags.DEFINE_integer(
    "evaluate_every", 500,
    "Evaluate model on dev set after this many steps (default: 100)")
tf.flags.DEFINE_integer(
    "print_loss", 200,
    "print loss message after this many steps (default: 100)")
tf.flags.DEFINE_integer("checkpoint_every", 300,
                        "Save model after this many steps (default: 100)")
tf.flags.DEFINE_integer("num_checkpoints", 5,
                        "Number of checkpoints to store (default: 5)")
# Misc Parameters
tf.flags.DEFINE_boolean("allow_soft_placement", True,
                        "Allow device soft device placement")
tf.flags.DEFINE_boolean("log_device_placement", False,
                        "Log placement of ops on devices")
tf.flags.DEFINE_boolean("is_restore", False,
                        "Allow to restore from checkpoits")
tf.flags.DEFINE_string(
    "embedding_type", "non_static",
    "rand, static,non_static, multiple_channels (default: 'rand')")
FLAGS = tf.flags.FLAGS


def train_step(cnn, train_summary_writer, sess, x_batch_train, y_batch_train):
    """
    A single training step
    """
    feed_dict = {
        cnn.input_x: x_batch_train,
        cnn.input_y: y_batch_train,
        cnn.dropout_keep_prob: FLAGS.dropout_keep_prob}
    _, step_train, summaries,\
        loss, acc_at_1 =\
        sess.run([cnn.train_op, cnn.global_step,
                  cnn.train_summary_op, cnn.cost, cnn.accuracy_at_1],
                 feed_dict)
    if step_train % FLAGS.print_loss == 0:
        time_str = datetime.datetime.now().isoformat()
        print(
            "{}: step {}, loss {:g}, acc_1 {:g}".format(time_str,
                                                        step_train,
                                                        loss,
                                                        acc_at_1))
    train_summary_writer.add_summary(summaries, step_train)
    return acc_at_1


def test_step(
        cnn,
        sess,
        x_batch_test,
        y_batch_test,
        step_test,
        writer=None):
    """
     Evaluates model on a dev set
    """
    feed_dict = {
        cnn.input_x: x_batch_test,
        cnn.input_y: y_batch_test,
        cnn.dropout_keep_prob: 1.0
    }
    summaries, loss,\
        streaming_accuray, prediction = \
        sess.run([cnn.test_summary_op,
                  cnn.cost,
                  cnn.streaming_accuray_op,
                  cnn.prediction],
                 feed_dict)
    if writer:
        writer.add_summary(summaries, step_test)
    return prediction, loss, streaming_accuray


def main(_):
    if not FLAGS.data_dir:
        raise ValueError("Must set --data_dir to  data directory")
    train_index = 1
    train_data = "eclipse/song_no_select/"
    embedding_file = FLAGS.data_dir + 'GoogleNews-vectors-negative300.bin'

    model_types = ["textcnn", "multi_layers_cnn",
                   "hierarchical_cnn", "textlstm",
                   "text_bilstm", "text_cnn_lstm"]
    model_type = "text_bilstm"
    assert model_type in model_types

    data_dir = FLAGS.data_dir + train_data
    data_results = data_dir + "results/" + model_type + '/'
    if not tf.gfile.Exists(data_results):
        tf.gfile.MakeDirs(data_results)
    FLAGS.checkpointDir = FLAGS.checkpointDir + model_type
    class_file = data_results + "class_" + str(train_index) + ".csv"
    data_files = [data_dir + str(i) + '.csv' for i in range(train_index + 1)]
    x_train, y_train, x_dev, y_dev, embedding, lb =\
        data_utls.load_files(data_files, class_file, embedding_file)
    config_model = {
        'num_filters': FLAGS.num_filters,
        'filter_sizes': list(map(int, FLAGS.filter_sizes.split(","))),
        'n_hidden': FLAGS.n_hidden,
        'embedding_type': FLAGS.embedding_type,
        'l2_reg_lambda': FLAGS.l2_reg_lambda,
        'learning_rate': FLAGS.learning_rate,
        'max_sent_length': x_train.shape[1],
        'num_classes': len(lb.classes_),
        'embedding_shape': embedding.shape
    }
    with tf.Graph().as_default():
        session_conf = tf.ConfigProto(
            allow_soft_placement=FLAGS.allow_soft_placement,
            log_device_placement=FLAGS.log_device_placement)

        sess = tf.Session(config=session_conf)
        with sess.as_default():
            cnn = Model(model_type=model_type, config_model=config_model)
            # Checkpoint directory. TensorFlow assumes this directory
            # already exists so we need to create it
            saver = tf.train.Saver(
                var_list=tf.trainable_variables(),
                max_to_keep=FLAGS.num_checkpoints)
            checkpoint_dir = os.path.abspath(
                os.path.join(FLAGS.checkpointDir, "checkpoints"))
            checkpoint_prefix = os.path.join(checkpoint_dir, "model")
            if FLAGS.is_restore and os.path.exists(checkpoint_dir):
                print("Restoring Variables from Checkpoint")
                saver.restore(sess,
                              tf.train.latest_checkpoint(checkpoint_dir))
                if FLAGS.embedding_type == 'static':
                    sess.run(tf.assign(cnn.embedding, embedding))
            else:
                if tf.gfile.Exists(FLAGS.checkpointDir):
                    tf.gfile.DeleteRecursively(FLAGS.checkpointDir)
                    tf.gfile.MakeDirs(FLAGS.checkpointDir)
                print("Creating Checkpoint file for restoring")
                os.makedirs(checkpoint_dir)
                # Initialize all variables
                sess.run(tf.global_variables_initializer())
                sess.run(tf.local_variables_initializer())
                if FLAGS.embedding_type in ['static', 'non_static',
                                            'multiple_channels']:
                    sess.run(tf.assign(cnn.embedding, embedding))
                    if FLAGS.embedding_type == 'multiple_channels':
                        sess.run(tf.assign(cnn.another_embedding, embedding))
            train_summary_dir = os.path.abspath(
                os.path.join(FLAGS.checkpointDir, "summaries", "train"))
            train_summary_writer = tf.summary.FileWriter(
                train_summary_dir, sess.graph)

            # Generate batches
            batches = data_utls.batch_generator(
                x_train, y_train, lb,
                FLAGS.batch_size, FLAGS.num_epochs,
                shuffle=True)
            # Training loop. For each batch...
            best_accuracy = 0.0
            last_improvement_step = 0
            numer_iter = int((len(y_train) - 1) / FLAGS.batch_size) + 1
            for batch, _ in batches:
                x_batch, y_batch = zip(*batch)
                accuracy = train_step(
                    cnn, train_summary_writer, sess, x_batch, y_batch)
                current_step = tf.train.global_step(sess, cnn.global_step)
                if current_step % FLAGS.checkpoint_every == 0:
                    path = saver.save(sess, checkpoint_prefix,
                                      global_step=current_step)
                    print("Saved model checkpoint to {}\n".format(path))
                if accuracy > best_accuracy:
                    best_accuracy = accuracy
                    last_improvement_step = current_step
                if ((current_step - last_improvement_step) >
                    (FLAGS.require_improvement * numer_iter) or
                        (best_accuracy == 1.0)):
                    print('no more improving!')
                    break
            current_step = tf.train.global_step(sess, cnn.global_step)
            path = saver.save(sess, checkpoint_prefix,
                              global_step=current_step)
            test_summary_dir = os.path.abspath(
                os.path.join(FLAGS.checkpointDir, "summaries", "test"))
            test_summary_writer = tf.summary.FileWriter(
                test_summary_dir, sess.graph)
            print("\n Testing:")
            dev_batches = data_utls.batch_generator(
                x_dev, y_dev, lb, FLAGS.batch_size)
            step = 0
            predictions = []
            labels = []
            for dev_batch, label in dev_batches:
                step += 1
                x_dev_batch, y_dev_batch = zip(*dev_batch)
                prediction, loss, streaming_accuray = test_step(
                    cnn, sess, x_dev_batch, y_dev_batch, step,
                    writer=test_summary_writer)
                if step % FLAGS.print_loss == 0:
                    time_str = datetime.datetime.now().isoformat()
                    print("{}: step {}, loss {:g},\
                        streaming_accuracy {:g}".format(time_str,
                                                        step, loss,
                                                        streaming_accuray))
                predictions.extend([lb.classes_[index]
                                    for index in prediction])
                labels.extend(label)

            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g},\
                        streaming_accuracy {:g}".format(time_str,
                                                        step, loss,
                                                        streaming_accuray))
            prediction_file = data_results + \
                "prediction_" + str(train_index) + ".csv"
            label_file = data_results + "label_" +\
                str(train_index) + ".csv"
        np.savetxt(prediction_file, predictions, fmt="%s", delimiter=',')
        np.savetxt(label_file, labels, fmt="%s", delimiter=',')


if __name__ == "__main__":
    FLAGS._parse_flags()
    print("\nParameters:")
    for attr, value in sorted(FLAGS.__flags.items()):
        print("{}={}".format(attr.upper(), value))
    print("")
    tf.app.run()
