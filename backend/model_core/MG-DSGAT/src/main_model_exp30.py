#!/usr/bin/env python36
# -*- coding: utf-8 -*-

""" 改引入的model為何(import), EXP_NAME
"""

import argparse
import os
import pickle
import time
import torch
# import wandb
import sys

# sys.path.append('../')
# from sklearn.model_selection import KFold
from model_exp30 import SessionGraph
from trainer import Trainer
from utils import DataSampler, split_validation, init_seed, get_multi_seed, infer_n_node

EXP_NAME = "Demo_model_exp30"

parser = argparse.ArgumentParser()
parser.add_argument('--dataset', default='Tmall', help='dataset name: /Tmall/Nowplaying/diginetica/yoochoose1_4/yoochoose1_64')
parser.add_argument('--batchSize', type=int, default=512, help='input batch size') #64,100,256,512
parser.add_argument('--hiddenSize', type=int, default=256, help='hidden state size')
parser.add_argument('--epochs', type=int, default=30, help='the number of epochs to train for')
parser.add_argument('--lr', type=float, default=0.001, help='learning rate')  # [0.001, 0.0005, 0.0001]
parser.add_argument('--lr_dc', type=float, default=0.1, help='learning rate decay rate')
parser.add_argument('--lr_dc_step', type=int, default=5, help='the number of steps after which the learning rate decay 3')
parser.add_argument('--l2', type=float, default=1e-5, help='l2 penalty')  # [0.001, 0.0005, 0.0001, 0.00005, 0.00001]
parser.add_argument('--step', type=int, default=1, help='gnn propogation steps')
parser.add_argument('--patience', type=int, default=3, help='the number of epoch to wait before early stop ')
# parser.add_argument('--nonhybrid', action='store_true', help='only use the global preference to predict')
parser.add_argument('--validation', action='store_true', help='validation')
# parser.add_argument('--kfold_num', type=int, default=5, help='k-fold number')
parser.add_argument('--valid_portion', type=float, default=0.2, help='split the portion of training set as validation set')
# parser.add_argument('--w_ne', type=float, default=1.7, help='neighbor weight') #digi：1.7 Tmall 0.9
parser.add_argument('--gama', type=float, default=1.7, help='cos_sim') #digi：1.7
parser.add_argument('--num_attention_heads', type=int, default=4, help='Multi-Att heads')
parser.add_argument('--neighbor_n', type=int, default=3, help='find neighbor number') # Diginetica:3; Tmall: 7; Nowplaying: 4
parser.add_argument('--seed', type=int, default=2023, help='random seed')
parser.add_argument('--num-workers', type=int, default=0)

# for group representation
parser.add_argument('--len-session', type=int, default=50, help='maximal session length')
parser.add_argument('--last_k', type=int, default=7, help='last k items for group representation')
parser.add_argument('--l_p', type=int, default=4, help='l_p norm for group representation')
parser.add_argument('--use_attn_conv', type=str, default="True")
parser.add_argument('--heads', type=int, default=8, help='number of attention heads')
parser.add_argument('--dot', default=True, action='store_true')

parser.add_argument('--use_multi_seeds', action='store_true', help='use multiple seeds for training')

opt = parser.parse_args()
# print(opt)
os.environ['CUDA_VISIBLE_DEVICES'] = '0,1,2'
torch.cuda.set_device(0)


def resolve_n_node(dataset):
    inferred_n_node = infer_n_node(dataset)
    if inferred_n_node is not None:
        print(f'Using inferred n_node={inferred_n_node} for dataset={dataset}')
        return inferred_n_node

    if dataset == 'diginetica':
        return 43098
    elif dataset == 'Nowplaying':
        return 60417
    elif dataset == 'Tmall':
        return 40728
    elif dataset == 'RetailRocket':
        return 36969
    elif dataset == 'Gowalla':
        return 29511

    raise ValueError(f'Unsupported dataset: {dataset}')

def main():
    # del all_train_seq, g
    n_node = resolve_n_node(opt.dataset)
    # elif opt.dataset == 'yoochoose1_64' or opt.dataset == 'yoochoose1_4':
    #     n_node = 37484
    if opt.dataset == 'Nowplaying':
        opt.neighbor_n = 4
    elif opt.dataset == 'Tmall':
        # opt.w_ne = 0.9
        opt.neighbor_n = 7
        opt.last_k = 3
        opt.step = 2 
    elif opt.dataset == 'Gowalla':
        opt.last_k = 4
    print(opt)

    

    if opt.use_multi_seeds:
        seeds = get_multi_seed(3)
        for seed in seeds:
            seed = init_seed(seed)
            print(seed)
        
            train_data = pickle.load(open('./datasets/' + opt.dataset + '/train.txt', 'rb'))
            train_data, valid_data = split_validation(train_data, opt.valid_portion)
            test_data = pickle.load(open('./datasets/' + opt.dataset + '/test.txt', 'rb'))
            test_data = DataSampler(opt, test_data, opt.len_session, train=False)
            test_loader = torch.utils.data.DataLoader(test_data, num_workers=opt.num_workers, batch_size=opt.batchSize, 
                                                            shuffle=False, pin_memory=False)
            
            model_save_file = EXP_NAME + "_" + opt.dataset + '_' + str(opt.batchSize) + '_seed_' + str(opt.seed)
            # tr_eval_run = wandb.init(
            #     # set the wandb project where this run will be logged
            #     project = opt.dataset + "_exp",
            #     # set a run name (otherwise it'll randomly assigned)
            #     name = EXP_NAME + "_" + str(opt.batchSize) + '_seed_' + str(seed),
            #     # track hyperparameters and run metadata
            #     config = opt,
            #     group = EXP_NAME + "_" + str(opt.batchSize)
            # )
            # config = tr_eval_run.config
            # config.update({"n_node": n_node})
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


            train_data = DataSampler(opt, train_data, opt.len_session, train=True)
            valid_data = DataSampler(opt, valid_data, opt.len_session, train=False)
            train_loader = torch.utils.data.DataLoader(train_data, num_workers=opt.num_workers, batch_size=opt.batchSize, 
                                                    shuffle=True, pin_memory=False)
            valid_loader = torch.utils.data.DataLoader(valid_data, num_workers=opt.num_workers, batch_size=opt.batchSize,
                                                        shuffle=False, pin_memory=False)
            

            model = SessionGraph(opt, n_node, device).to(device)
            runner = Trainer(opt.dataset, model, train_loader, valid_loader, test_loader, device, opt, model_save_file)
            start = time.time()
            final_test_result, best_model_test_result = runner.train(opt.epochs)
            end = time.time()
            print("Run time: %f s" % (end - start))
            # tr_eval_run.finish()

    elif opt.validation:
        seed = init_seed(opt.seed)
        print(seed)
        
        train_data = pickle.load(open('./datasets/' + opt.dataset + '/train.txt', 'rb'))
        train_data, valid_data = split_validation(train_data, opt.valid_portion)
        test_data = pickle.load(open('./datasets/' + opt.dataset + '/test.txt', 'rb'))
        test_data = DataSampler(opt, test_data, opt.len_session, train=False)
        test_loader = torch.utils.data.DataLoader(test_data, num_workers=opt.num_workers, batch_size=opt.batchSize, 
                                                        shuffle=False, pin_memory=False)
        
        model_save_file = EXP_NAME + "_" + opt.dataset + '_' + str(opt.batchSize) + '_seed_' + str(opt.seed) + '-last_k_' + str(opt.last_k)
        # tr_eval_run = wandb.init(
        #     # set the wandb project where this run will be logged
        #     project = opt.dataset + "_exp",
        #     # set a run name (otherwise it'll randomly assigned)
        #     name = EXP_NAME + "_" + str(opt.batchSize) + '_layer_' + str(opt.step),
        #     # track hyperparameters and run metadata
        #     config = opt,
        #     group = EXP_NAME + "_" + str(opt.batchSize) + '_layer'
        # )
        # config = tr_eval_run.config
        # config.update({"n_node": n_node})
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        train_data = DataSampler(opt, train_data, opt.len_session, train=True)
        valid_data = DataSampler(opt, valid_data, opt.len_session, train=False)
        train_loader = torch.utils.data.DataLoader(train_data, num_workers=opt.num_workers, batch_size=opt.batchSize, 
                                                shuffle=True, pin_memory=False)
        valid_loader = torch.utils.data.DataLoader(valid_data, num_workers=opt.num_workers, batch_size=opt.batchSize,
                                                    shuffle=False, pin_memory=False)
        

        model = SessionGraph(opt, n_node, device).to(device)
        runner = Trainer(opt.dataset, model, train_loader, valid_loader, test_loader, device, opt, model_save_file)
        start = time.time()
        final_test_result, best_model_test_result = runner.train(opt.epochs)
        end = time.time()
        print("Run time: %f s" % (end - start))

        # tr_eval_run.finish()


if __name__ == '__main__':
    main()
