"""YOLOX-S fine-tuning experiment for Store Vision inventory (box + packet).

Used with YOLOX's tools/train.py:

    python tools/train.py -f finetune/exps/yolox_s_box_packet.py \
        -d 1 -b 8 --fp16 -o -c yolox_s.pth

- Same yolox-s backbone (depth 0.33 / width 0.50) so we can start from the
  pretrained yolox_s.pth weights.
- num_classes = 2 (box, packet) — the two-model setup: person/vehicle stay with
  the COCO model, this model only learns inventory.
- Settings are tuned for a small (~200-300 image) dataset: fewer epochs, gentler
  augmentation, frequent eval.

Set the dataset location with the YOLOX_DATA_DIR env var (the Colab notebook
does this); otherwise it defaults to finetune/dataset relative to CWD.
"""
import os

from yolox.exp import Exp as MyExp


class Exp(MyExp):
    def __init__(self):
        super().__init__()

        # --- yolox-s architecture (must match the pretrained checkpoint) ---
        self.depth = 0.33
        self.width = 0.50
        self.exp_name = "yolox_s_box_packet"

        # --- dataset ---
        self.num_classes = 2  # box, packet  (keep in sync with finetune/classes.txt)
        self.data_dir = os.environ.get("YOLOX_DATA_DIR", "finetune/dataset")
        self.train_ann = "instances_train2017.json"
        self.val_ann = "instances_val2017.json"

        # --- schedule (light fine-tune) ---
        self.max_epoch = 50
        self.warmup_epochs = 1
        self.no_aug_epochs = 15          # turn off mosaic/mixup for the last epochs
        self.eval_interval = 5
        self.print_interval = 20
        self.data_num_workers = 2

        # --- augmentation (gentler for a small dataset) ---
        self.mosaic_prob = 0.5
        self.mixup_prob = 0.5
        self.hsv_prob = 1.0
        self.flip_prob = 0.5

        # input size
        self.input_size = (640, 640)
        self.test_size = (640, 640)
        self.basic_lr_per_img = 0.01 / 64.0
