"""YOLOX-S fine-tuning experiment for Store Vision — single combined model.

8 classes: person, bicycle, car, motorcycle, bus, truck, box, packet
(kept in sync with finetune/classes.txt).

Person + vehicle boxes are auto-labeled by the existing COCO model
(finetune/scripts/autolabel_coco.py); box + packet are hand-labeled. The merged
dataset trains ONE model that detects everything.

Used with YOLOX's tools/train.py:

    python tools/train.py -f finetune/exps/yolox_s_store.py \
        -d 1 -b 8 --fp16 -o -c yolox_s.pth

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
        self.exp_name = "yolox_s_store"

        # --- dataset ---
        self.num_classes = 8  # person, bicycle, car, motorcycle, bus, truck, box, packet
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
