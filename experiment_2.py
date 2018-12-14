import sys
import csv
import time

import numpy as np
import pandas as pd

from collections import defaultdict

from scipy.io import arff

from tstransform.evaluation import failures
from tstransform.evaluation import differences
from tstransform.evaluation import cost

from tstransform.transform import NearestNeighbourLabelTransformer
from tstransform.transform import GreedyTreeLabelTransform
from tstransform.transform import IncrementalTreeLabelTransform
from tstransform.transform import LockingIncrementalTreeLabelTransform


def group_labels(y):
    tmp = defaultdict(list)
    for i, label in enumerate(y):
        tmp[label].append(i)

    label_index = {label: np.array(arr) for label, arr in tmp.items()}
    return dict(label_index)


two_class_datasets = [
    "Computers",
    "MoteStrain",
    "Ham",
    #    "FordA",
    "DistalPhalanxOutlineCorrect",
    "MiddlePhalanxOutlineCorrect",
    "PhalangesOutlinesCorrect",
    "Earthquakes",
    "Lightning2",
    "GunPoint",
    "ItalyPowerDemand",
    "TwoLeadECG",
    "ProximalPhalanxOutlineCorrect",
    "ECG200",
    "Herring",
    "ToeSegmentation2",
    "HandOutlines",
    "ToeSegmentation1",
    "WormsTwoClass",
    "ECGFiveDays",
    "Wine",
    "BirdChicken",
    "SonyAIBORobotSurface2",
    #    "FordB",
    "Strawberry",
    "SonyAIBORobotSurface1",
    "Coffee",
    "Wafer",
    "BeetleFly",
    "Yoga",
]

result_writer = csv.writer(sys.stdout)
result_writer.writerow([
    "dataset",
    "method",
    "k",
    "to_label",
    "cost",
    "failures",
    "differences",
    "predictions",
    "pruned_transform",
    "score",
    "total_n_transform",
    "total_n_test",
    "total_n_not_to_label",
    "transform_time",
])

# k in [0, 10], n in [0, 1000], m in [0, 600]
multi_class_datasets = [
    "SyntheticControl",  # shape:(600, 60), classes:6
    "CBF",  # shape:(930, 128), classes:3
    "OSULeaf",  # shape:(442, 427), classes:6
    "ArrowHead",  # shape:(211, 251), classes:3
    "Fish",  # shape:(350, 463), classes:7
    "Car",  # shape:(120, 577), classes:4
    "MiddlePhalanxTW",  # shape:(553, 80), classes:6
    "Lightning7",  # shape:(143, 319), classes:7
    "DiatomSizeReduction",  # shape:(322, 345), classes:4
    "Meat",  # shape:(120, 448), classes:3
    "ProximalPhalanxTW",  # shape:(605, 80), classes:6
    "DistalPhalanxOutlineAgeGroup",  # shape:(539, 80), classes:3
    "ProximalPhalanxOutlineAgeGroup",  # shape:(605, 80), classes:3
    "MiddlePhalanxOutlineAgeGroup",  # shape:(554, 80), classes:3
    "DistalPhalanxTW",  # shape:(539, 80), classes:6
    "Beef",  # shape:(60, 470), classes:5
    "Plane",  # shape:(210, 144), classes:7
    "OliveOil",  # shape:(60, 570), classes:4
    "Trace",  # shape:(200, 275), classes:4
    "FaceFour",  # shape:(112, 350), classes:4
]

train_fraction = 0.8
random_seed = 10
for k in [1]:
    for dataset_name in multi_class_datasets:
        rnd = np.random.RandomState(random_seed)

        data, meta = arff.loadarff(
            "TSC Problems/{0}/{0}.arff".format(dataset_name))
        df = pd.DataFrame(data)
        x = df.iloc[:, :-1].values
        y = df.iloc[:, -1].values.astype(int)

        idx = np.arange(x.shape[0])
        rnd.shuffle(idx)

        train_size = round(x.shape[0] * train_fraction)

        x_train = x[idx[:train_size], :]
        y_train = y[idx[:train_size]]

        x_test = x[idx[train_size:], :]
        y_test = y[idx[train_size:]]

        label_index = group_labels(y_test)

        print(
            "{} of shape: {}, and {} with labels {}".format(
                dataset_name,
                x_train.shape,
                x_test.shape,
                label_index.keys(),
            ),
            file=sys.stderr)
        print(
            "Label sizes: {}".format(
                [(lbl, len(lbl_idx)) for lbl, lbl_idx in label_index.items()]),
            file=sys.stderr)

        nn_trans = NearestNeighbourLabelTransformer(n_neighbors=k)
        greedy_e_trans = IncrementalTreeLabelTransform(
            epsilon=1,
            random_state=random_seed,
            n_shapelets=100,
            n_jobs=8,
            batch_size=0.05,
        )
        incremental_e_trans = LockingIncrementalTreeLabelTransform(
            epsilon=1,
            random_state=random_seed,
            n_jobs=8,
        )

        for to_label in label_index.keys():
            nn_trans.fit(x_train, y_train, to_label)

            if greedy_e_trans.paths_ is None:
                greedy_e_trans.fit(x_train, y_train, to_label)
                incremental_e_trans.__dict__ = greedy_e_trans.__dict__

                nn_score = nn_trans.score(x_test, y_test)
                e_score = greedy_e_trans.score(x_test, y_test)
            else:
                greedy_e_trans.to_label_ = to_label
                incremental_e_trans.to_label_ = to_label

            methods = {
                "NN": (nn_trans, nn_score),
                "IE": (greedy_e_trans, e_score),
                "LIE": (incremental_e_trans, e_score)
            }
            for name, (trans, score) in methods.items():
                x_test_not_to = x_test[trans.predict(x_test) != to_label]
                if x_test_not_to.shape[0] == 0:
                    continue
                t = time.time()
                x_prime = trans.transform(x_test_not_to)
                t = time.time() - t
                c = cost(x_prime, x_test_not_to)
                d = differences(x_prime, x_test_not_to, axis=1)
                f = failures(x_prime) / float(x_test_not_to.shape[0])
                result_writer.writerow([
                    dataset_name,
                    name,
                    k,
                    to_label,
                    c,
                    f,
                    d,
                    trans.predictions_,
                    trans.pruned_,
                    score,
                    x_test_not_to.shape[0],
                    x_test.shape[0],
                    y_test[y_test != to_label].shape[0],
                    t * 1000,  # ms
                ])
