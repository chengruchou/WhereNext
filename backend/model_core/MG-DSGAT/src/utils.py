import json
import os
import torch
import random
import time
import numpy as np
import copy
from torch.utils.data import Dataset


def init_seed(seed=None):
    """Fixed random seed"""
    if seed is None or seed == 0:
        seed = int(time.time() * 1000 // 1000)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    np.random.seed(seed)
    random.seed(seed)

    return seed

def get_multi_seed(n_seeds: int=5):
    seeds = [random.randint(1, 2**32 - 1) for _ in range(n_seeds)]
    return seeds


def infer_n_node(dataset, dataset_root='./datasets'):
    """Infer n_node from dataset artifacts when available.

    Priority:
    1. build_manifest.json -> stats.n_node_for_model
    2. raw_location2item.json -> len(mapping) + 1

    Returns None when no artifact is available so callers can fall back to
    the historical hardcoded values.
    """
    dataset_dir = os.path.join(dataset_root, dataset)
    manifest_path = os.path.join(dataset_dir, 'build_manifest.json')
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        stats = manifest.get('stats', {})
        n_node = stats.get('n_node_for_model')
        if n_node is not None:
            return int(n_node)

    raw2item_path = os.path.join(dataset_dir, 'raw_location2item.json')
    if os.path.exists(raw2item_path):
        with open(raw2item_path, 'r', encoding='utf-8') as f:
            raw2item = json.load(f)
        return int(len(raw2item) + 1)

    return None


def split_validation(train_set: tuple, valid_portion: float) -> (tuple, tuple):
    """Split the training set into training set and validation set."""
    train_set_x, train_set_y = train_set
    n_samples = len(train_set_x)
    sidx = np.arange(n_samples, dtype='int32')
    np.random.shuffle(sidx)
    n_train = int(np.round(n_samples * (1. - valid_portion)))
    valid_set_x = [train_set_x[s] for s in sidx[n_train:]]
    valid_set_y = [train_set_y[s] for s in sidx[n_train:]]
    train_set_x = [train_set_x[s] for s in sidx[:n_train]]
    train_set_y = [train_set_y[s] for s in sidx[:n_train]]

    return (train_set_x, train_set_y), (valid_set_x, valid_set_y)


def handle_data(inputs, train_len=None):
    len_data = [len(nowData) for nowData in inputs]
    max_len = max(len_data)
    us_pois = [upois + [0] * (max_len - le) for upois, le in zip(inputs, len_data)]
    us_msks = [[1] * le + [0] * (max_len - le) for le in len_data]
    return us_pois, us_msks, max_len


def build_graph(items, inputs, alias_inputs):
    """Build graph for each session and shorten the item list in the batch.
    
    Args:
        items: item list of each session. (B, len_max)
        inputs: input session list. (B, len_max)
        alias_inputs: ... (B, len_max)

    Return:
        adj: adjacency matrix. (B, S, 2S) in+out
        re_items: shorten item list. (B, S)([B, len_max] --> [B, S])
    """
    adj, re_items = [], []
    max_n_node = 0
    for u_item in items:
        p_len = len(np.unique(u_item))
        if p_len > max_n_node:
            max_n_node = p_len
    for u_item in items:
        re_items.append(u_item[:max_n_node])
    # --- Test for exp18 ---
    # n_node = []
    # for u_input in inputs:
    #     n_node.append(len(np.unique(u_input)))
    # n_node = torch.tensor(n_node).long()
    # ----------------------
    # max_n_node = np.max(n_node)
    for i in range(len(inputs)):
        # node = np.unique(inputs[i])
        # items.append(node.tolist() + (max_n_node - len(node)) * [0])
        u_A = np.zeros((max_n_node, max_n_node))
        for j in range(len(alias_inputs[i]) - 1):
            if inputs[i][j+1].item() == 0:
                break
            u = alias_inputs[i][j].item()
            v = alias_inputs[i][j+1].item()
            u_A[u][v] = 1
        u_sum_in = np.sum(u_A, 0)
        u_sum_in[np.where(u_sum_in == 0)] = 1
        u_A_in = np.divide(u_A, u_sum_in)
        u_sum_out = np.sum(u_A, 1)
        u_sum_out[np.where(u_sum_out == 0)] = 1
        u_A_out = np.divide(u_A.transpose(), u_sum_out)
        u_A = np.concatenate([u_A_in, u_A_out]).transpose()
        adj.append(u_A)
    
    return adj, re_items


def get_overlap(sessions):
    """Get overlap matrix and degree matrix.
        
    Args:
        sessions: a batch of sessions. (B, S)
    
    Return:
        matrix: overlap matrix.
        degree: degree matrix.
    """
    matrix = np.zeros((len(sessions), len(sessions)))
    for i in range(len(sessions)):
        # get unique items except 0
        seq_a = set(sessions[i])
        seq_a.discard(0)
        for j in range(i+1, len(sessions)):
            seq_b = set(sessions[j])
            seq_b.discard(0)
            overlap = seq_a.intersection(seq_b)
            ab_set = seq_a | seq_b
            # undirected graph (weight = overlap / ab_set)
            matrix[i][j] = float(len(overlap)) / float(len(ab_set))
            matrix[j][i] = matrix[i][j]
    matrix = matrix + np.diag([1.0]*len(sessions)) # A + I
    degree = np.sum(np.array(matrix), 1)
    degree = np.diag(1.0/degree) # D^-1

    return matrix, degree


class DataSampler(Dataset):
    def __init__(self, opt, sessions, max_len, train=True):
        self.opt = opt
        inputs, mask, len_max = handle_data(sessions[0], max_len)
        self.sessions = sessions[0]
        self.inputs = np.asarray(inputs)
        self.targets = np.asarray(sessions[1])
        self.mask = np.asarray(mask)
        self.length = len(sessions[0])
        self.max_len = len_max
        # self.num_node = num_node
        # self.vn_id = num_node + 1
        self.train = train

    def get_data(self, idx):
        u_input, mask, target = self.inputs[idx], self.mask[idx], self.targets[idx]

        node = np.unique(u_input)
        items = node.tolist() + (self.max_len - len(node)) * [0]
        alias_inputs = [np.where(node == i)[0][0] for i in u_input]

        if len(alias_inputs) != len(u_input):
            raise ValueError(
                f"Alias length mismatch at sample {idx}: "
                f"len(alias_inputs)={len(alias_inputs)}, len(u_input)={len(u_input)}"
            )
        if len(alias_inputs) > 0:
            alias_array = np.asarray(alias_inputs)
            if alias_array.min() < 0 or alias_array.max() >= len(node):
                raise IndexError(
                    f"Alias index out of bounds at sample {idx}: "
                    f"alias_min={int(alias_array.min())}, alias_max={int(alias_array.max())}, "
                    f"node_count={len(node)}, session={u_input.tolist()}, node={node.tolist()}"
                )
        if target <= 0:
            raise ValueError(f"Invalid non-positive target at sample {idx}: target={int(target)}")

        return u_input, mask, target, items, alias_inputs

    def __getitem__(self, index):
        u_input, mask, target, items, alias_inputs = self.get_data(index)


        return {"alias_inputs": torch.tensor(alias_inputs),
                "items": torch.tensor(items),
                "mask": torch.tensor(mask),
                "targets": torch.tensor(target),
                "inputs": torch.tensor(u_input),
                "index": torch.tensor(index),
                }

    def __len__(self):
        return self.length
