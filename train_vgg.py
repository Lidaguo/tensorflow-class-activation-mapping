import os

import numpy as np

from class_activation_map import *
from read_caltech import read_caltech
from utils import load_image
from utils import restore
from vgg16 import vgg16


def sanity_check(sess, vgg):
    from scipy.misc import imread, imresize
    from imagenet_classes import class_names
    img1 = imread('laska.png', mode='RGB')
    img1 = imresize(img1, (224, 224))
    prob = sess.run(vgg.probs, feed_dict={vgg.images_placeholder: [img1]})[0]
    preds = (np.argsort(prob)[::-1])[0:5]
    for p in preds:
        print(class_names[p], prob[p])


if __name__ == '__main__':
    f_log = open('vgg_log.txt', 'w')
    weight_path = 'vgg16_weights.npz'
    model_path = './models/caltech256/'
    n_epochs = 10000
    init_learning_rate = 1e-4
    # weight_decay_rate = 0.0005
    use_cam = False
    momentum = 0.9
    batch_size = 2  # 60
    im_width = 224

    images_tf = tf.placeholder(tf.float32, [None, im_width, im_width, 3], name='images')
    labels_tf = tf.placeholder(tf.int64, [None], name='labels')

    sess = tf.Session()
    model = vgg16(images_tf, weight_path, sess, class_activation_map=use_cam, num_classes=2)
    top_conv = model.pool5
    y = model.output  # softmax-output of the model after GAP.

    if use_cam:
        class_activation_map = get_class_map(0, top_conv, im_width, gap_w=model.gap_w)
        sess.run(tf.initialize_variables([model.gap_w]))

    loss_tf = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(y, labels_tf))

    # weights_only = filter(lambda x: x.name.endswith('W:0'), tf.trainable_variables())
    # weight_decay = tf.reduce_sum(tf.pack([tf.nn.l2_loss(x) for x in weights_only])) * weight_decay_rate
    # loss_tf += weight_decay

    learning_rate = tf.placeholder(tf.float32, [])
    train_step = tf.train.GradientDescentOptimizer(learning_rate).minimize(loss_tf)

    # sess.run(tf.initialize_all_variables())  # should not be called here.

    saver = tf.train.Saver(tf.all_variables(), max_to_keep=10)
    step_start = restore(sess, saver, query='checkpoints/caltech*')

    train_set, test_set, label_dict, n_labels = read_caltech(force_generation=True, max_label_count=2)
    iterations = 0
    loss_list = []

    sanity_check(sess, model)

    for epoch in range(n_epochs):

        train_set.index = list(range(len(train_set)))
        train_set = train_set.ix[np.random.permutation(len(train_set))]

        for start, end in zip(
                range(0, len(train_set) + batch_size, batch_size),
                range(batch_size, len(train_set) + batch_size, batch_size)):

            current_data = train_set[start:end]
            current_image_paths = current_data['image_path'].values
            current_images = np.array(list(map(lambda x: load_image(x, im_width), current_image_paths)))
            good_index = np.array(list(map(lambda x: x is not None, current_images)))

            current_data = current_data[good_index]
            current_images = np.stack(current_images[good_index])
            current_labels = current_data['label'].values

            print('evaluating...')
            _, loss_val, output_val = sess.run(
                [train_step, loss_tf, y],
                feed_dict={
                    learning_rate: init_learning_rate,
                    images_tf: current_images,
                    labels_tf: current_labels
                })
            print('loss = {}'.format(loss_val))
            print(' ... DONE')

            loss_list.append(loss_val)

            iterations += 1
            if iterations % 5 == 0:
                print('======================================')
                print('Epoch', epoch, 'Iteration', iterations)
                print('Processed', start, '/', len(train_set))

                label_predictions = output_val.argmax(axis=1)
                acc = (label_predictions == current_labels).sum()

                print('Accuracy:', acc, '/', len(current_labels))
                print('Training Loss:', np.mean(loss_list))
                print('\n')
                loss_list = []

        n_correct = 0
        n_data = 0
        for start, end in zip(
                range(0, len(test_set) + batch_size, batch_size),
                range(batch_size, len(test_set) + batch_size, batch_size)
        ):
            current_data = test_set[start:end]
            current_image_paths = current_data['image_path'].values
            current_images = np.array(map(lambda x: load_image(x), current_image_paths))

            good_index = np.array(map(lambda x: x is not None, current_images))

            current_data = current_data[good_index]
            current_images = np.stack(current_images[good_index])
            current_labels = current_data['label'].values

            output_vals = sess.run(y, feed_dict={images_tf: current_images})

            label_predictions = output_vals.argmax(axis=1)
            acc = (label_predictions == current_labels).sum()

            n_correct += acc
            n_data += len(current_data)

        acc_all = n_correct / float(n_data)
        f_log.write('epoch:' + str(epoch) + '\tacc:' + str(acc_all) + '\n')
        print('$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$')
        print('epoch:' + str(epoch) + '\tacc:' + str(acc_all) + '\n')
        print('$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$')

        saver.save(sess, os.path.join(model_path, 'model'), global_step=epoch)

        init_learning_rate *= 0.99


        # grads_and_vars = optimizer.compute_gradients(loss_tf)

        # new_grads_and_vars = []
        # for gv in grads_and_vars:
        #    if 'conv5_3' in gv[1].name or 'GAP' in gv[1].name:
        #        print('Keeping gradient the same for {}'.format(gv[1].name))
        #        new_grads_and_vars.append((gv[0], gv[1]))
        #    else:
        #        print('0.1 * gradient for {}'.format(gv[1].name))
        #        new_grads_and_vars.append((gv[0] * 0.1, gv[1]))

        # grads_and_vars = map(
        #    lambda gv: (gv[0], gv[1]) if ('conv5_3' in gv[1].name or 'GAP' in gv[1].name) else (gv[0] * 0.1, gv[1]),
        #    grads_and_vars)

        # train_op = optimizer.apply_gradients(new_grads_and_vars)