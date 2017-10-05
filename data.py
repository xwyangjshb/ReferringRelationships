"""Converts a dataset into the format we expect for training.
"""

from keras.applications.vgg16 import preprocess_input
from keras.preprocessing import image

import argparse
import cv2
import json
import numpy as np
import sys
import os

class VRDDataset(): def __init__(self, data_path, img_dir, im_metadata_path, num_subjects=100, num_predicates=70, num_objects=100, im_dim=224):
        self.data = json.load(open(data_path))
        self.im_metadata = json.load(open(im_metadata_path))
        self.im_dim = im_dim
        self.col_template = np.arange(self.im_dim).reshape(1, self.im_dim)
        self.row_template = np.arange(self.im_dim).reshape(self.im_dim, 1)
        self.img_dir = img_dir
        self.train_image_idx = []
        self.val_image_idx = []
        self.num_subjects = num_subjects
        self.num_predicates = num_predicates
        self.num_objects = num_objects

    def rescale_bbox_coordinates(self, obj, im_metadata):
        """
        :param object: object coordinates
        :param im_metadata: image size and width
        :return: rescaled top, left, bottom, right coordinates
        """
        h_ratio = self.im_dim * 1. / im_metadata['height']
        w_ratio = self.im_dim * 1. / im_metadata['width']
        y_min, y_max, x_min, x_max = obj['bbox']
        return y_min * h_ratio, x_min * w_ratio, min(y_max * h_ratio, self.im_dim - 1), min(x_max * w_ratio,
                                                                                            self.im_dim - 1)

    def get_regions_from_bbox(self, bbox):
        """
        :param bbox: tuple (top, left, bottom, right) coordinates of the object of interest
        :return: converts bbox given as to image array with 0 or 1 for ground truth regions
        """
        top, left, bottom, right = bbox
        col_indexes = (1 * (self.col_template > left) * (self.col_template < right)).repeat(self.im_dim, 0)
        row_indexes = (1 * (self.row_template > top) * (self.row_template < bottom)).repeat(self.im_dim, 1)
        return col_indexes * row_indexes

    def get_train_val_splits(self, val_split, shuffle=True):
        """
        :param val_split: float, proportion of validation examples
        :return: train image ids (list) and validation image ids (list)
        """
        #TODO: Add seed
        image_idx = list(self.data.keys())
        if shuffle:
            np.random.shuffle(image_idx)
        thresh = int(len(image_idx) * (1. - val_split))
        self.train_image_idx = image_idx[:thresh]
        self.val_image_idx = image_idx[thresh:]
        return self.train_image_idx, self.val_image_idx

    def build_dataset(self, image_idx):
        """
        :param image_idx: list of image ids
        :return: images ids (each image ids is repeated for each relationship within that image),
        relationships (Nx3 array with subject, predicate and object categories)
        subject and object bounding boxes (each Nx4)
        """
        subjects_bbox = []
        objects_bbox = []
        relationships = []
        image_ids = []
        for i, image_id in enumerate(image_idx):
            im_data = self.im_metadata[image_id]
            for j, relationship in enumerate(self.data[image_id]):
                image_ids += [image_id]
                subject_id = relationship['subject']['category']
                relationship_id = relationship['predicate']
                object_id = relationship['object']['category']
                relationships += [(subject_id, relationship_id, object_id)]
                s_region = self.rescale_bbox_coordinates(relationship['subject'], im_data)
                o_region = self.rescale_bbox_coordinates(relationship['object'], im_data)
                subjects_bbox += [s_region]
                objects_bbox += [o_region]
        return np.array(image_ids), np.array(relationships), np.array(subjects_bbox), np.array(objects_bbox)

    def build_and_save_dataset(self, save_dir, image_idx=None):
        """
        :param image_idx: list of image ids
        :return: images ids (each image ids is repeated for each relationship within that image),
        relationships (Nx3 array with subject, predicate and object categories)
        subject and object bounding boxes (each Nx4)
        """
        rel_idx = []
        relationships = []
        if not image_idx:
            image_idx = self.data.keys()
        nb_images = len(image_idx)
        for i, image_id in enumerate(image_idx):
            im_data = self.im_metadata[image_id]
            if i%100==0:
                print('{}/{} images processed'.format(i, nb_images))
            for j, relationship in enumerate(self.data[image_id]):
                rel_id = image_id.split('.')[0] + '-{}'.format(j)
                rel_idx += [rel_id]
                subject_id = relationship['subject']['category']
                predicate_id = relationship['predicate']
                object_id = relationship['object']['category']
                relationships += [(subject_id, predicate_id, object_id)]
                s_bbox = self.rescale_bbox_coordinates(relationship['subject'], im_data)
                o_bbox= self.rescale_bbox_coordinates(relationship['object'], im_data)
                s_region = self.get_regions_from_bbox(s_bbox) #* 255
                o_region = self.get_regions_from_bbox(o_bbox) #* 255#TODO:this is just to visualize regions, needs to me removed afterwards
                cv2.imwrite(os.path.join(save_dir, '{}-s.jpg'.format(rel_id)), s_region)
                cv2.imwrite(os.path.join(save_dir, '{}-o.jpg'.format(rel_id)), o_region)
        np.save(os.path.join(save_dir, 'rel_idx.npy'), np.array(rel_idx))
        np.save(os.path.join(save_dir, 'relationships.npy'), np.array(relationships))

    def get_image_from_img_id(self, img_id):
        img_path = os.path.join(self.img_dir, img_id)
        img = image.load_img(img_path, target_size=(224, 224))
        img_array = image.img_to_array(img)
        img_array = np.expand_dims(img_array, axis=0)
        img_array = preprocess_input(img_array)
        return img_array[0]

    def get_images(self, image_idx):
        images = np.zeros((len(image_idx), self.im_dim, self.im_dim, 3))
        for i, image_id in enumerate(image_idx):
            images[i] = self.get_image_from_img_id(image_id)
        return images

    def get_images_and_regions(self, image_idx, subject_bbox, object_bbox):
        m = len(image_idx)
        images = np.zeros((m, self.im_dim, self.im_dim, 3))
        s_regions = np.zeros((m, self.im_dim * self.im_dim))
        o_regions = np.zeros((m, self.im_dim * self.im_dim))
        for i, image_id in enumerate(image_idx):
            s_bbox = subject_bbox[i]
            o_bbox = object_bbox[i]
            images[i] = self.get_image_from_img_id(image_id)
            s_regions[i] = self.get_regions_from_bbox(s_bbox)
            o_regions[i] = self.get_regions_from_bbox(o_bbox)
        return images, s_regions, o_regions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Dataset creation for Visual '
                                     'Relationship model. This scripts saves '
                                     'masks for objects and subjects in '
                                     'directories, as well as numpy arrays '
                                     'for relationships.')
    parser.add_argument('--test', action='store_true',
                        help='When true, the data is not split into training '
                        'and validation sets')
    parser.add_argument('--val-split', type=float, default=0.1,
                        help='validation split')
    parser.add_argument('--save-dir', type=str, default=None,
                        help='where to save the ground truth masks, this '
                        'Location where dataset should be saved.')
    parser.add_argument('--img-dir', type=str, default=None,
                        help='Location where images are stored.')
    parser.add_argument('--annotations', type=str,
                        default='data/VRD/annotations_train.json',
                        help='Json with relationships for each image.')
    parser.add_argument('--image-metadata', type=str,
                        default='data/VRD/image_metadata.json',
                        help='Image metadata json file.')
    args = parser.parse_args()

    # Make sure that the required fields are present.
    if args.save_dir is None:
        print '--save-dir not specified. Exiting!'
        sys.exit(0)
    if args.img_dir is None:
        print '--img-dir not specified. Exiting!'
        sys.exit(0)

    vrd_dataset = VRDDataset(args.annotations, args.img_dir,
                             args.image_metadata)
    if args.test:
        test_dir = os.path.join(args.save_dir, 'test')
        os.mkdir(test_dir)
        vrd_dataset.build_and_save_dataset(test_dir)
    else:
        train_split, val_split = vrd_dataset.get_train_val_splits(
            args.val_split)
        train_dir = os.path.join(args.save_dir, 'train')
        os.mkdir(train_dir)
        print('| Building training data...')
        vrd_dataset.build_and_save_dataset(train_dir, train_split)
        val_dir = os.path.join(args.save_dir, 'val')
        os.mkdir(val_dir)
        print('| Building validation data...')
        vrd_dataset.build_and_save_dataset(val_dir, val_split)
