import numpy as np
import time
import torch
from torch import nn
from collections import defaultdict

import wandb



def prepare_batch(batch):
    batch_dict = {
        "alias_inputs": batch["alias_inputs"].cuda().long(), # (B, len_max)
        "items": batch["items"].cuda().long(), # (B, S)
        "mask": batch["mask"].cuda().long(), # (B, len_max)
        "targets": batch["targets"].cuda().long(), # (B, 1)
        "inputs": batch["inputs"].cuda().long(), # (B, len_max)
        "index": batch["index"].cuda().long(), # (B, 1)
    }

    return batch_dict


def evaluate(model, data_loader, device, Ks=[5, 10, 20]):
    model.eval()
    total_val_loss = 0
    # hit = []
    # mrr = []
    num_samples = 0
    results = defaultdict(float)

    with torch.no_grad():
        for batch, step in zip(data_loader, np.arange(len(data_loader))):
            batch = prepare_batch(batch)
            batch_num = len(batch['inputs'])
            targets, scores = model(batch)
            val_loss = nn.CrossEntropyLoss()(scores, targets-1)
            total_val_loss += val_loss.item()
            avg_val_loss = total_val_loss / (step + 1)
            
            sub_scores = scores.topk(20)[1]
            targets = targets.unsqueeze(1)
            num_samples += batch_num


            for K in Ks:
                hits = torch.where(sub_scores[:, :K] == (targets-1))[1] + 1
                hits = hits.float().cpu()
                results[f'HR@{K}'] += hits.numel()
                results[f'MRR@{K}'] += hits.reciprocal().sum().item()
        
        for metric in results:
            results[metric] = (results[metric] / num_samples) * 100

    return results, avg_val_loss


class Trainer:
    def __init__(self, dataset, model, train_loader, valid_loader, test_loader, device, opt, model_save_file):
        self.dataset = dataset
        self.model = model
        self.train_loader = train_loader
        self.valid_loader = valid_loader
        self.test_loader = test_loader
        self.device = device
        self.patience = opt.patience
        self.model_save_file = model_save_file
        self.Ks = [5, 10, 20]

    def _train_epoch(self):
        total_loss = 0
        total_con_loss = 0
        self.model.train()
        for batch, step in zip(self.train_loader, np.arange(len(self.train_loader))):
            batch = prepare_batch(batch)
            self.model.optimizer.zero_grad()


            targets, scores = self.model(batch)
            loss = nn.CrossEntropyLoss()(scores, targets-1)

            loss.backward()
            self.model.optimizer.step()
            total_loss += loss.item()

            avg_train_loss = total_loss / (step + 1)
            avg_con_loss = total_con_loss / (step + 1)
            
            # Logging Training & Evaluation Step Info.
            if step % int(len(self.train_loader) / 5 + 1) == 0:
                print('Step[%d/%d]: Avg Train Loss: %.4f' % (step, len(self.train_loader), avg_train_loss))
                # wandb.log({"Step_avg_train_loss": avg_train_loss})
                
                # Logging Step Evaluation Info.
                _, avg_val_loss = evaluate(self.model, self.valid_loader, self.device, Ks=self.Ks)
                print('\tAvg Val Loss: %.4f' % (avg_val_loss))
                # wandb.log({"Step_avg_val_loss": avg_val_loss})
                self.model.train()

        return avg_train_loss, avg_con_loss

    def train(self, epochs):
        # max_hit = 0
        # max_mrr = 0
        bad_counter = 0
        results = defaultdict(float)
        max_result = defaultdict(float)
        for K in self.Ks:
            max_result[f"HR@{K}"] = 0
            max_result[f"MRR@{K}"] = 0

        for epoch in range(epochs):
            t = time.time()
            avg_train_loss, avg_con_loss = self._train_epoch()
            # Logging Train Info.
            print('Epoch:[%d/%d] Avg Train Loss: %.4f, Avg Con-Loss: %.4f' % (epoch+1, epochs, avg_train_loss, avg_con_loss))
            # wandb.log({"epoch": epoch+1, "Epoch_avg_train_loss": avg_train_loss, "Epoch_avg_con_loss": avg_con_loss})

            # Evaluation
            results, avg_val_loss = evaluate(self.model, self.valid_loader, self.device)
            self.model.scheduler.step()

            # Logging Evaluation Info.
            print(f'Avg Val Loss: {avg_val_loss}')
            # wandb.log({"Epoch_avg_val_loss": avg_val_loss})
            for K in self.Ks:
                print(f'\tVal HR@{K}: {results[f"HR@{K}"]}, Val MRR@{K}: {results[f"MRR@{K}"]}')
                # wandb.log({f"Val HR@{K}": results[f"HR@{K}"], f"Val MRR@{K}": results[f"MRR@{K}"]})

            any_better = False
            for metric in results:
                if results[metric] > max_result[metric]:
                    max_result[metric] = results[metric]
                    any_better = True
            
            if any_better:
                bad_counter = 0
                # save validation best model
                BEST_PATH = './save_model/' + self.model_save_file + "_best_model.pt"
                torch.save(self.model.state_dict(), BEST_PATH)
            else:
                bad_counter += 1
                if bad_counter == self.patience:
                    # save after early stopping model
                    FINAL_PATH = './save_model/' + self.model_save_file + "_final_model.pt"
                    torch.save(self.model.state_dict(), FINAL_PATH)
                    # wandb.log({"bad_counter": bad_counter})
                    break

            # wandb.log({"bad_counter": bad_counter})
            print('========= Epoch Elapsed Time: %.2fs =========' % (time.time() - t))
        
        # Running Test
        tmp_final_test_result, _ = evaluate(self.model, self.test_loader, self.device)
        self.model.load_state_dict(torch.load(BEST_PATH))
        tmp_best_model_test_result, _ = evaluate(self.model, self.test_loader, self.device)
        for K in self.Ks:
            print(f'Final Test Result: HR@{K}: {tmp_final_test_result[f"HR@{K}"]}, MRR@{K}: {tmp_final_test_result[f"MRR@{K}"]}')
            print(f'Best Model Test Result: HR@{K}: {tmp_best_model_test_result[f"HR@{K}"]}, MRR@{K}: {tmp_best_model_test_result[f"MRR@{K}"]}')
            # wandb.log({f"Final_Test_HR@{K}": tmp_final_test_result[f"HR@{K}"], f"Final_Test_MRR@{K}": tmp_final_test_result[f"MRR@{K}"]})
            # wandb.log({f"Best_Model_Test_HR@{K}": tmp_best_model_test_result[f"HR@{K}"], f"Best_Model_Test_MRR@{K}": tmp_best_model_test_result[f"MRR@{K}"]})
        
        return tmp_final_test_result, tmp_best_model_test_result