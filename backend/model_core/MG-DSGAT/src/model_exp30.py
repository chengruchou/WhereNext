#!/usr/bin/env python36
# -*- coding: utf-8 -*-
"""
Created on July, 2018

@author: Tangrizzly
"""

import datetime
import math
import time
from math import sqrt
import numpy as np
import torch
from torch import nn
from torch.nn import Module, Parameter
import torch.nn.functional as F
import torch.nn.init as init
from numba import jit
from entmax import entmax_bisect

from utils import build_graph, get_overlap


class LayerNorm(Module):
    def __init__(self, hidden_size, eps=1e-12) -> None:
        super(LayerNorm, self).__init__()
        self.weight = Parameter(torch.ones(hidden_size))
        self.bias = Parameter(torch.zeros(hidden_size))
        self.variance_epsilon = eps
    
    def forward(self, x):
        u = x.mean(-1, keepdim=True)
        s = (x-u).pow(2).mean(-1, keepdim=True)
        x = (x-u) / torch.sqrt(s + self.variance_epsilon)
        return self.weight * x + self.bias

class GNN(Module):
    def __init__(self, hidden_size, step=1) -> None:
        super(GNN, self).__init__()
        self.step = step
        self.hidden_size = hidden_size

        self.input_size = self.hidden_size * 2
        self.gate_size = 3 * self.hidden_size
        self.w_ih = Parameter(torch.Tensor(self.gate_size, self.input_size))
        self.w_hh = Parameter(torch.Tensor(self.gate_size, self.hidden_size))
        self.b_ih = Parameter(torch.Tensor(self.gate_size))
        self.b_hh = Parameter(torch.Tensor(self.gate_size))
        self.b_iah = Parameter(torch.Tensor(self.hidden_size))
        self.b_oah = Parameter(torch.Tensor(self.hidden_size))

        self.linear_edge_in = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
        self.linear_edge_out = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
    
    def GNNCell(self, A, hidden):
        """ Calculate each GNN layer."""
        # A: (B, S, 2S) 圖的鄰接矩陣
        # hidden: (B, S, 2D) 用戶序列的embedding (item embedding + position embedding)
        input_in = torch.matmul(A[:, :, :A.shape[1]], self.linear_edge_in(hidden)) + self.b_iah # (B, S, 2D) = (B, S, S) * {(B, S, 2D) * (B, 2D, 2D)}
        input_out = torch.matmul(A[:, :, A.shape[1]:2*A.shape[1]], self.linear_edge_out(hidden)) + self.b_oah # (B, S, 2D) 
        inputs = torch.cat([input_in, input_out], 2) # (B, S, 4D)
        gi = F.linear(inputs, self.w_ih, self.b_ih) # (B, S, 6D) = (B, S, 4D) * (B, 6D, 4D)^T
        gh = F.linear(hidden, self.w_hh, self.b_hh) # (B, S, 6D) = (B, S, 2D) * (B, 6D, 2D)^T
        i_r, i_i, i_n = gi.chunk(3, 2) # 三個W*a (B, S, 2D)
        h_r, h_i, h_n = gh.chunk(3, 2) # 三個U*v (B, S, 2D)
        reset_gate = torch.sigmoid(i_r + h_r)
        input_gate = torch.sigmoid(i_i + h_i)
        new_gate = torch.tanh(i_n + reset_gate * h_n)
        hy = (1 - input_gate) * hidden + input_gate * new_gate # newgate + inputgate * (hidden - newgate)
        
        return hy
    
    def forward(self, A, hidden):
        for i in range(self.step):
            hidden = self.GNNCell(A, hidden)
        return hidden
    
class FindNeighbors(Module):
    def __init__(self, opt, hidden_size) -> None:
        super(FindNeighbors, self).__init__()
        self.hidden_size = hidden_size
        self.neighbor_n = opt.neighbor_n # Diginetica:3; Tmall: 7; Nowplaying: 4
        self.dropout40 = nn.Dropout(0.4)

    def compute_sim(self, sess_emb):
        # sess_emb: (B, D)
        fenzi = torch.matmul(sess_emb, sess_emb.permute(1, 0)) # (B, B)
        fenmu_l = torch.sum(sess_emb * sess_emb + 0.000001, 1)
        fenmu_l = torch.sqrt(fenmu_l).unsqueeze(1) # (B, 1)
        fenmu = torch.matmul(fenmu_l, fenmu_l.permute(1, 0)) # (B, B)
        cos_sim = fenzi / fenmu # (B, B)
        cos_sim = nn.Softmax(dim=-1)(cos_sim)
        return cos_sim

    def forward(self, sess_emb):
        k_v = self.neighbor_n
        cos_sim = self.compute_sim(sess_emb) # (B, B)
        if cos_sim.size()[0] < k_v:
            k_v = cos_sim.size()[0]
        cos_topk, topk_indices = torch.topk(cos_sim, k=k_v, dim=1) # (B, k_v)
        cos_topk = nn.Softmax(dim=-1)(cos_topk)
        sess_topk = sess_emb[topk_indices] # (B, k_v, D)

        cos_sim = cos_topk.unsqueeze(2).expand(cos_topk.size()[0], cos_topk.size()[1], self.hidden_size) # (B, k_v, D)

        neighbor_sess = torch.sum(cos_sim * sess_topk, 1) # (B, D)
        neighbor_sess = self.dropout40(neighbor_sess)
        return neighbor_sess
    
class RelationGAT(Module):
    def __init__(self, batch_size, hidden_size=100) -> None:
        super(RelationGAT, self).__init__()
        self.batch_size = batch_size
        self.dim = hidden_size
        self.w_f = nn.Linear(2*hidden_size, hidden_size)
        self.alpha_w = nn.Linear(self.dim, 1)
        self.atten_w0 = nn.Parameter(torch.Tensor(1, self.dim))
        self.atten_w1 = nn.Parameter(torch.Tensor(self.dim, self.dim))
        self.atten_w2 = nn.Parameter(torch.Tensor(self.dim, self.dim))
        self.atten_bias = nn.Parameter(torch.Tensor(self.dim))

    def get_alpha(self, x):
        # x: (B, 1, D)
        alpha_global = torch.sigmoid(self.alpha_w(x)) + 1 # (B, 1, 1)
        alpha_global = self.add_value(alpha_global)
        return alpha_global

    def add_value(self, value):
        mask_value = (value == 1).float()
        value = value.masked_fill(mask_value == 1, 1.00001)
        return value

    def tglobal_attention(self, target, k, v, alpha_ent=1):
        # target: (B, 1, D), k: (B, S, D), v: (B, S, D)
        alpha = torch.matmul(torch.relu(k.matmul(self.atten_w1) + target.matmul(self.atten_w2) + self.atten_bias), self.atten_w0.t())
        # alpha: (B, S, 1), alpha_ent: (B, 1, 1)
        alpha = entmax_bisect(alpha, alpha_ent, dim=1) # (B, S, 1)
        c = torch.matmul(alpha.transpose(1, 2), v) # (B, 1, D)
        return c

    def forward(self, item_embedding, items, A, D, target_embedding):
        # item_embedding: (N, D), items: (B, S), target_embedding: (B, 1, D)
        # get item embedding of each session
        seq_h = []
        for i in torch.arange(items.shape[0]):
            seq_h.append(torch.index_select(item_embedding, 0, items[i])) # (B, S, D)
        seq_h1 = torch.stack(seq_h, dim=0) # (B, S, D)
        
        len = seq_h1.shape[1] # S
        relation_emb_gcn = torch.sum(seq_h1, 1) # (B, D) Aggregate node info. --> Get session representation
        DA = torch.matmul(D, A) # (B, B)  D^-1*(A+I)
        relation_emb_gcn = torch.matmul(DA, relation_emb_gcn) # (B, D)
        relation_emb_gcn = relation_emb_gcn.unsqueeze(1).expand(relation_emb_gcn.shape[0], len, relation_emb_gcn.shape[1]) # (B, S, D)

        # target_emb = self.w_f(target_embedding) # (B, 1, D)
        alpha_line = self.get_alpha(x = target_embedding) # (B, 1, 1)
        q = target_embedding # (B, 1, D)
        k = relation_emb_gcn # (B, S, D)
        v = relation_emb_gcn # (B, S, D)

        line_c = self.tglobal_attention(q, k, v, alpha_ent=alpha_line)  # (B, 1, D)
        c = torch.selu(line_c).squeeze(1)  # (B, D)
        l_c = c / (torch.norm(c, dim=-1, keepdim=True) + 1e-12)  # (B, D)

        return l_c
    

class LastAttention(Module):
    def __init__(self, hidden_size, heads, dot, l_p, last_k=3, use_attn_conv=False, area_func=None):
        super().__init__()
        # self.dim = 2*hidden_size
        self.hidden_size = hidden_size
        self.heads = heads
        self.last_k = last_k
        self.linear_zero = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
        self.linear_one = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
        self.linear_two = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
        self.linear_three = nn.Linear(self.hidden_size, self.heads, bias=False)
        self.linear_four = nn.Linear(self.hidden_size, self.hidden_size, bias=False)
        self.linear_five = nn.Linear(self.hidden_size, self.hidden_size, bias=False)
        self.dropout = 0.1
        self.dot = dot
        self.l_p = l_p
        self.use_attn_conv = use_attn_conv
        # self.ccattn = area_func
        self.last_layernorm = torch.nn.LayerNorm(self.hidden_size, eps=1e-8)
        self.reset_parameters()
    
    def reset_parameters(self):
        for weight in self.parameters():
            weight.data.normal_(std=0.1)

    def forward(self, ht1, hidden, mask):
        # ht1: (B, last_k, D), hidden: (B, len_max, D), mask: (B, len_max)
        q0 = self.linear_zero(ht1).view(-1, ht1.size(1), self.hidden_size // self.heads)
        q1 = self.linear_one(hidden).view(-1, hidden.size(1), self.hidden_size // self.heads)
        q2 = self.linear_two(hidden).view(-1, hidden.size(1), self.hidden_size // self.heads)
        assert not torch.isnan(q0).any()
        assert not torch.isnan(q1).any()
        
        alpha = torch.sigmoid(torch.matmul(q0, q1.permute(0, 2, 1)))
        assert not torch.isnan(alpha).any()
        alpha = alpha.view(-1, q0.size(1) * self.heads, hidden.size(1)).permute(0, 2, 1)
        alpha = torch.softmax(2 * alpha, dim=1)
        assert not torch.isnan(alpha).any()
        if self.use_attn_conv == "True":
            m = torch.nn.LPPool1d(self.l_p, self.last_k, stride=self.last_k)
            alpha = m(alpha)
            alpha = torch.masked_fill(alpha, ~mask.bool().unsqueeze(-1), float('-inf'))
            alpha = torch.softmax(2 * alpha, dim=1)
        alpha = F.dropout(alpha, p=self.dropout, training=self.training)
        a = torch.sum(
            (alpha.unsqueeze(-1) * q2.view(hidden.size(0), -1, self.heads, self.hidden_size // self.heads)).view(
                hidden.size(0), -1, self.hidden_size) * mask.view(mask.shape[0], -1, 1).float(), 1)
        
        return a, alpha

class SessionGraph(Module):
    def __init__(self, opt, n_node, device):
        super(SessionGraph, self).__init__()
        self.dataset = opt.dataset
        self.n_node = n_node
        self.device = device
        self.hidden_size = opt.hiddenSize
        self.batch_size = opt.batchSize
        self.embedding = nn.Embedding(self.n_node, self.hidden_size, padding_idx=0, max_norm=1.5)
        self.pos_embedding = nn.Embedding(300, self.hidden_size, padding_idx=0, max_norm=1.5)
        self.gnn_layers = getattr(opt, "ggnn_layers", opt.step)
        self.gnn = GNN(self.hidden_size, step=self.gnn_layers)

        # Sparse Graph Attention
        self.is_dropout = True
        self.w = 20
        dim = self.hidden_size * 2 # 2D
        self.dim = dim
        self.LN = nn.LayerNorm(self.hidden_size)
        self.dropout = nn.Dropout(0.2)
        self.activate = F.relu
        self.atten_w0 = nn.Parameter(torch.Tensor(1, self.hidden_size))
        self.atten_w1 = nn.Parameter(torch.Tensor(self.hidden_size, self.hidden_size))
        self.atten_w2 = nn.Parameter(torch.Tensor(self.hidden_size, self.hidden_size))
        self.atten_bias = nn.Parameter(torch.Tensor(self.hidden_size))
        self.attention_mlp = nn.Linear(self.hidden_size, self.hidden_size)
        self.self_atten_w1 = nn.Linear(self.hidden_size, self.hidden_size)
        self.self_atten_w2 = nn.Linear(self.hidden_size, self.hidden_size)
        self.alpha_w = nn.Linear(self.hidden_size, 1)
        self.linear_zero = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
        self.linear_one = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
        self.linear_two = nn.Linear(self.hidden_size, self.hidden_size, bias=True)

        # Group representation
        self.last_k = opt.last_k
        self.l_p = opt.l_p
        self.use_attn_conv = opt.use_attn_conv
        self.heads = opt.heads
        self.dot = opt.dot
        self.linear_grp = nn.Linear(2*self.hidden_size, self.hidden_size)
        self.grp_sess_weight = nn.Linear(self.hidden_size, 1)
        self.linear_q = nn.ModuleList()
        for i in range(self.last_k):
            self.linear_q.append(nn.Linear((i+1)*self.hidden_size, self.hidden_size))
        self.mattn = LastAttention(self.hidden_size, self.heads, self.dot, self.l_p, last_k=self.last_k,
                                  use_attn_conv=self.use_attn_conv)

        # Multi
        self.num_attention_heads = opt.num_attention_heads
        self.attention_head_size = int(self.hidden_size / self.num_attention_heads)
        self.multi_alpha_w = nn.Linear(self.attention_head_size, 1)

        # Neighbor
        self.FindNeighbor = FindNeighbors(opt, self.hidden_size)

        # Relation Conv
        self.RelationGraph = RelationGAT(self.batch_size, self.hidden_size)
        self.LayerNorm = LayerNorm(2*self.hidden_size, eps=1e-12)
        self.linear_one = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
        self.linear_two = nn.Linear(self.hidden_size, self.hidden_size, bias=True)
        self.w_f = nn.Linear(2*self.hidden_size, self.hidden_size)

        # concat
        self.linear_transform = nn.Linear(2*self.hidden_size, self.hidden_size)

        self.loss_function = nn.CrossEntropyLoss()
        self.optimizer = torch.optim.Adam(self.parameters(), lr=opt.lr, weight_decay=opt.l2)
        self.scheduler = torch.optim.lr_scheduler.StepLR(self.optimizer, step_size=opt.lr_dc_step, gamma=opt.lr_dc)
        self.reset_parameters()

    def reset_parameters(self):
        stdv = 1.0 / math.sqrt(self.hidden_size)
        for weight in self.parameters():
            weight.data.uniform_(-stdv, stdv)

    def add_position_embedding(self, seq_hidden):
        """Add position embeddings.
        
        Create item and position embedding respectively, and then concate them together.

        Args:
            seq_hidden: a batch of sequence, shape -> (B, len_max, D)
        
        Return:
            sequence_embeddings: added position embeddings' sequence_emb, shape -> (B, S, 2D)
        """

        batch_size = seq_hidden.shape[0] # B
        seq_len = seq_hidden.shape[1] # len_max

        position_ids = torch.arange(seq_len, dtype=torch.long, device=seq_hidden.device) # (len_max, )
        position_ids = torch.flip(position_ids, [0]) # (len_max, ) reverse position
        position_ids = position_ids.unsqueeze(0).repeat(batch_size, 1) # (B, len_max)
        position_embeddings = self.pos_embedding(position_ids) # (B, len_max, D)
        # item_embeddings = self.embedding(seq_hidden) # (B, S, D)

        sequence_embeddings = torch.cat((seq_hidden, position_embeddings), -1) # (B, len_max, 2D)
        sequence_embeddings = self.LayerNorm(sequence_embeddings)

        return sequence_embeddings

    def get_alpha(self, x=None, seq_len=70, number=None):
        # X: (B, 1, D)
        if number == 0:
            alpha_ent = torch.sigmoid(self.alpha_w(x)) + 1
            alpha_ent = self.add_value(alpha_ent).unsqueeze(1)
            alpha_ent = alpha_ent.expand(-1, seq_len, -1)
            return alpha_ent
        if number == 1:
            alpha_global = torch.sigmoid(self.alpha_w(x)) + 1 # (B, 1, 1)
            alpha_global = self.add_value(alpha_global)
            return alpha_global

    def get_alpha2(self, x, seq_len): # x shape: (B, H, D/H)
        alpha_ent = torch.sigmoid(self.multi_alpha_w(x)) + 1 # (B, H, 1)
        alpha_ent = self.add_value(alpha_ent).unsqueeze(2) # (B, H, 1, 1)
        alpha_ent = alpha_ent.expand(-1, -1, seq_len, -1) # (B, H, len_max+1, 1)
        return alpha_ent
    
    def add_value(self, value):
        # I think this module is to replace 1 with 1.00001 (Lin_chia)
        # if value = 1, it equals to use softmax
        mask_value = (value == 1).float()
        value = value.masked_fill(mask_value == 1, 1.00001)
        return value

    def transpose_for_scores(self, x):
        new_x_shape = x.size()[:-1] + (self.num_attention_heads, self.attention_head_size)
        x = x.view(*new_x_shape) # (B, len_max+1, H, D/H)
        return x.permute(0, 2, 1, 3) # (B, H, len_max+1, D/H)

    def Multi_Self_attention(self, q, k, v, sess_len):
        is_droupout = True

        query_layer = self.linear_zero(q) # (B, len_max+1, D)
        key_layer = self.linear_one(k) # (B, len_max+1, D)
        value_layer = self.linear_two(v) # (B, len_max+1, D)
        query_layer = self.transpose_for_scores(query_layer) # (B, H, len_max+1, D/H)
        key_layer = self.transpose_for_scores(key_layer) # (B, H, len_max+1, D/H)
        value_layer = self.transpose_for_scores(value_layer) # (B, H, len_max+1, D/H)

        attention_scores = torch.matmul(query_layer, key_layer.transpose(-1, -2)) # (B, H, len_max+1, len_max+1)
        attention_scores = attention_scores / math.sqrt(self.attention_head_size)

        # input target node embedding (last one)
        alpha_ent = self.get_alpha2(query_layer[:, :, -1, :], seq_len=sess_len) # (B, H, len_max+1, 1)
        attention_probs = entmax_bisect(attention_scores, alpha_ent, dim=-1) # (B, H, len_max+1, len_max+1)
        context_layer = torch.matmul(attention_probs, value_layer) # (B, H, len_max+1, D/H)

        context_layer = context_layer.permute(0, 2, 1, 3).contiguous() # (B, len_max+1, H, D/H)
        new_context_layer_shape = context_layer.size()[:-2] + (self.hidden_size,)
        att_v = context_layer.view(*new_context_layer_shape) # (B, len_max+1, D)

        if is_droupout:
            att_v = self.dropout(self.self_atten_w2(self.activate(self.self_atten_w1(att_v)))) + att_v
        else:
            att_v = self.self_atten_w2(self.activate(self.self_atten_w1(att_v))) + att_v
        att_v = self.LN(att_v)
        c = att_v[:, -1, :].unsqueeze(1) # Target node (B, 1, D)
        x_n = att_v[:, :-1, :] # (B, len_max, D)

        return c, x_n
    
    def global_attention(self, target, k, v, mask=None, alpha_ent=1):
        alpha = torch.matmul(torch.relu(k.matmul(self.atten_w1) + target.matmul(self.atten_w2) + self.atten_bias), self.atten_w0.t()) # (B, len_max, 1)
        if mask is not None: # (B, len_max)
            mask = mask.unsqueeze(-1) # (B, len_max, 1)
            alpha = alpha.masked_fill(mask == 0, -np.inf)
        alpha = entmax_bisect(alpha, alpha_ent, dim=1)
        c = torch.matmul(alpha.transpose(1, 2), v) # (B, 1, D)
        return c

    def decoder(self, global_s, target_s):
        # global_s: (B, 1, D), target_s: (B, 1, D)
        if self.is_dropout:
            c = self.dropout(torch.selu(self.w_f(torch.cat((global_s, target_s), 2))))
        else:
            c = torch.selu(self.w_f(torch.cat((global_s, target_s), 2)))
        
        c = c.squeeze(1)  # (B, D)
        l_c = c / (torch.norm(c, dim=-1, keepdim=True) + 1e-12)
        return l_c


    def fusion_module(self, intra_sess_hidden, inter_sess_hidden, grp_sess_hidden):
        """Fuse intra-session, inter-session and group-session representations"""
        # sess_final = self.linear_transform(torch.cat((grp_sess_hidden, intra_sess_hidden, inter_sess_hidden), 1)) # (B, 3D)
        # sess_final = self.linear_transform(torch.cat((grp_sess_hidden, sess_final), 1)) # (B, 2D)
        sess_final = intra_sess_hidden + inter_sess_hidden
        
        # grp_weight = self.grp_sess_weight(grp_sess_hidden) # (B, 1) # torch.sigmoid()
        grp_weight = torch.sigmoid(self.grp_sess_weight(grp_sess_hidden)) # (B, 1)
        
        sess_final = sess_final + grp_weight * grp_sess_hidden
        # Dropout & Normalize
        if self.is_dropout:
            sess_final = self.dropout(torch.selu(sess_final))
        else:
            sess_final = torch.selu(sess_final)
        sess_final = sess_final.squeeze(1) if sess_final.dim() == 3 and sess_final.size(1) == 1 else sess_final
        sess_final = sess_final / (torch.norm(sess_final, dim=-1, keepdim=True) + 1e-12)

        return sess_final

    def _raise_batch_index_error(self, message, batch, extra=None):
        sample_indices = batch['index'].detach().cpu().tolist() if 'index' in batch else []
        payload = [
            message,
            f"dataset={self.dataset}",
            f"sample_indices={sample_indices[:8]}",
        ]
        if extra is not None:
            payload.append(extra)
        raise IndexError(' | '.join(payload))

    def _validate_batch(self, batch):
        items = batch['items']
        inputs = batch['inputs']
        targets = batch['targets']

        if torch.any(items < 0):
            self._raise_batch_index_error('Negative item id found in batch items', batch)
        if torch.any(inputs < 0):
            self._raise_batch_index_error('Negative item id found in batch inputs', batch)
        if torch.any(targets <= 0):
            self._raise_batch_index_error('Non-positive target id found', batch)

        max_item_id = int(torch.max(torch.maximum(items.max(), inputs.max())).item())
        max_target_id = int(targets.max().item())
        max_id = max(max_item_id, max_target_id)
        if max_id >= self.n_node:
            self._raise_batch_index_error(
                'Global item id exceeds embedding range',
                batch,
                extra=f'max_id={max_id}, n_node={self.n_node}, valid_item_range=[0, {self.n_node - 1}]'
            )

    def _validate_alias_inputs(self, node_repr, alias_inputs, batch):
        if alias_inputs.dim() != 2:
            self._raise_batch_index_error(
                'alias_inputs must be rank-2',
                batch,
                extra=f'alias_inputs_shape={tuple(alias_inputs.shape)}'
            )

        if alias_inputs.size(0) != node_repr.size(0):
            self._raise_batch_index_error(
                'Batch size mismatch between alias_inputs and hidden',
                batch,
                extra=f'alias_batch={alias_inputs.size(0)}, hidden_batch={node_repr.size(0)}'
            )

        if torch.any(alias_inputs < 0):
            self._raise_batch_index_error('Negative alias index found', batch)

        max_alias = int(alias_inputs.max().item()) if alias_inputs.numel() > 0 else -1
        if max_alias >= node_repr.size(1):
            self._raise_batch_index_error(
                'Local alias index exceeds hidden node dimension',
                batch,
                extra=f'max_alias={max_alias}, hidden_nodes={node_repr.size(1)}'
            )

    def compute_scores(self, grp_hidden, hidden, mask, target_emb, att_hidden, relation_emb):
        # ht為local_embedding (最後一個item的embedding)
        ht = hidden[torch.arange(mask.shape[0]).long(), torch.sum(mask, 1) - 1] # (B, D)
        q1 = self.linear_one(ht).view(ht.shape[0], 1, ht.shape[1]) # (B, 1, D)
        q2 = self.linear_two(hidden) # (B, len_max, D)

        sess_global = torch.sigmoid(q1 + q2) # (B, len_max, D)

        # Atten-Mixer
        ht0 = grp_hidden[torch.arange(mask.size(0)).long(), torch.sum(mask, 1) - 1] # Get last one emb. (B, D)
        hts = []
        lengths = torch.sum(mask, 1) # (B, 1)

        # Group representation. (Get last_1 to last_k group representations)
        for i in range(self.last_k):
            hts.append(torch.mean(torch.stack(
                [grp_hidden[torch.arange(mask.size(0)).long(), torch.clamp(lengths - (j + 1), -1, 1000)] for j in
                 range(i + 1)]), dim=0).unsqueeze(1))
        
        hts = torch.cat(hts, dim=1) # (B, last_k, D)
        hts = hts.div(torch.norm(hts, p=2, dim=1, keepdim=True) + 1e-12) 

        grp_hidden = grp_hidden[:, :mask.size(1)] # (B, len_max, D)
        ais, weights = self.mattn(hts, grp_hidden, mask)

        grp_sess = self.linear_grp(torch.cat((ais, ht0), dim=1))
        grp_sess = grp_sess.div(torch.norm(grp_sess, p=2, dim=1, keepdim=True) + 1e-12) 
        

        # Sparse Global Attention
        alpha_global = self.get_alpha(x = target_emb, number = 1) # (B, 1, 1)
        q = target_emb # (B, 1, D)
        k = att_hidden # (B, len_max, D)
        v = sess_global # (B, len_max, D)
        global_c = self.global_attention(q, k, v, mask=mask, alpha_ent=alpha_global) # (B, 1, D)
        # Get integrated session representations
        sess_final = self.decoder(global_c, target_emb) # (B, D)
        
        sess_final = self.fusion_module(sess_final, relation_emb, grp_sess)

        # SIC
        neighbor_sess = self.FindNeighbor(sess_final)
        sess_final = sess_final + neighbor_sess # (B, D)

        # because our item index starting at 1, we need to skip 0
        b = self.embedding.weight[1:] / torch.norm(self.embedding.weight[1:], dim=-1).unsqueeze(1) # Normalize (N-1, D)
        scores = self.w * torch.matmul(sess_final, b.transpose(1, 0)) # (B, N)


        return scores

    def encoder(self, inputs, A, alias_inputs, A_hat, D_hat, batch):

        seq_emb = self.embedding(inputs) # (B, S, D)
        hidden = self.gnn(A, seq_emb) # (B, S, D)
        self._validate_alias_inputs(hidden, alias_inputs, batch)
        
        # Get embedding of each item in the session(last hidden layer)
        get = lambda i: hidden[i][alias_inputs[i]]
        seq_hidden_gnn = torch.stack([get(i) for i in torch.arange(len(alias_inputs)).long()]) # (B, len_max, D)
        seq_grp_hidden_gnn = torch.stack([get(i) for i in torch.arange(len(alias_inputs)).long()]) # (B, len_max, D)

        # Add zero vector(Target node) to last item embedding
        zeros = seq_hidden_gnn.new_zeros(seq_hidden_gnn.shape[0], 1, self.hidden_size) # (B, 1, D)
        session_target = torch.cat([seq_hidden_gnn, zeros], 1) # (B, len_max+1, D)

        sess_len = session_target.shape[1]
        target_emb, x_n = self.Multi_Self_attention(session_target, session_target, session_target, sess_len)
        relation_emb = self.RelationGraph(self.embedding.weight, inputs, A_hat, D_hat, target_emb)

        return seq_grp_hidden_gnn, seq_hidden_gnn, target_emb, x_n, relation_emb
    
    def forward(self, batch):
        self._validate_batch(batch)
        A, re_items = build_graph(batch['items'].cpu().numpy(), batch['inputs'].cpu().numpy(), batch['alias_inputs'])
        A_hat, D_hat = get_overlap(re_items)
        # A_hat, D_hat = get_overlap(batch['items'])
        
        device = batch['items'].device
        A = torch.as_tensor(np.asarray(A), dtype=torch.float32, device=device) # (B, S, 2S) in+out
        items = torch.as_tensor(np.asarray(re_items), dtype=torch.long, device=device) # (B, S)
        A_hat = torch.as_tensor(np.asarray(A_hat), dtype=torch.float32, device=device) # (B, B)
        D_hat = torch.as_tensor(np.asarray(D_hat), dtype=torch.float32, device=device) # (B, B)

        # items, inputs, mask, alias_inputs, pos_last_items, neg_last_items, neg_targets, targets = batch['items'], batch['inputs'], batch['mask'], batch['alias_inputs'], batch['pos_last_items'], batch['neg_last_items'], batch['neg_targets'], batch['targets']
        mask, alias_inputs, targets = batch['mask'], batch['alias_inputs'], batch['targets']

        self._validate_alias_inputs(items, alias_inputs, batch)
        seq_grp_hidden, hidden, target_emb, att_hidden, relation_emb = self.encoder(items, A, alias_inputs, A_hat, D_hat, batch)

        scores = self.compute_scores(seq_grp_hidden, hidden, mask, target_emb, att_hidden, relation_emb)

        
        return targets, scores
        
