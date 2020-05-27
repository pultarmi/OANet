import numpy as np
import argparse
import os
import glob
from tqdm import tqdm
import cv2
import h5py
import torch
from PIL import Image
import torchvision.transforms as transforms


def str2bool(v):
    return v.lower() in ("true", "1")


# Parse command line arguments.
parser = argparse.ArgumentParser(description='extract sift.')
parser.add_argument('--input_path', type=str, default='../raw_data/yfcc100m/',
                    help='Image directory or movie file or "camera" (for webcam).')
parser.add_argument('--img_glob', type=str, default='*/*/images/*.jpg',
                    help='Glob match if directory of images is specified (default: \'*/images/*.jpg\').')
parser.add_argument('--num_kp', type=int, default='2000',
                    help='keypoint number, default:2000')
parser.add_argument('--suffix', type=str, default='sift-2000',
                    help='suffix of filename, default:sift-2000')

default_resize_transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize(32),
    transforms.ToTensor()
])

class ExtractSIFT(object):
    def __init__(self, num_kp, contrastThreshold=1e-5):
        self.model = torch.jit.load('h8E512lib+colo+notrebs9000ep40PCA128lib.jitpt').cuda()
        print('model loaded')
        self.sift = cv2.xfeatures2d.SIFT_create(nfeatures=num_kp, contrastThreshold=contrastThreshold)

    def run(self, img_path):
        img = cv2.imread(img_path)
        cv_kp, desc = self.sift.detectAndCompute(img, None)
        print(desc.shape)
        kp = np.array([[_kp.pt[0], _kp.pt[1], _kp.size, _kp.angle] for _kp in cv_kp])  # N*4
        # print(img.shape)

        patches = []
        img = Image.fromarray(img, 'RGB').convert('L')
        for k in kp:
            D2pt = k
            left, top, right, bottom = D2pt[0] - 32, D2pt[1] - 32, D2pt[0] + 32, D2pt[1] + 32
            # if not (left > 0 and top > 0 and right < w - 1 and bottom < h - 1):  # no black rectangles
            #     continue
            patch = img.crop((left, top, right, bottom))
            patch = torch.tensor(np.asarray(patch))
            patch = default_resize_transform(patch)
            patches += [patch]
            # patch = patch.cuda().unsqueeze(0)

        patches = torch.stack(patches)
        bs = 1024
        one_descs = []
        n_patches = len(patches)
        n_batches = int(n_patches / bs + 1)
        for batch_idx in range(n_batches):
            st = batch_idx * bs
            if (batch_idx == n_batches - 1) and ((batch_idx + 1) * bs > n_patches):
                end = n_patches
            else:
                end = (batch_idx + 1) * bs
            if st >= end:
                continue
            # data_a = patches[st:end].astype(np.float32)
            # data_a = torch.from_numpy(data_a).cuda().detach()
            data_a = patches[st:end]
            with torch.no_grad():
                out_a = self.model(data_a)
            one_descs.append(out_a.data.cpu().numpy())
        descs = np.concatenate(one_descs)
        return kp, desc


def write_feature(pts, desc, filename):
    with h5py.File(filename, "w") as ifp:
        ifp.create_dataset('keypoints', pts.shape, dtype=np.float32)
        ifp.create_dataset('descriptors', desc.shape, dtype=np.float32)
        ifp["keypoints"][:] = pts
        ifp["descriptors"][:] = desc


if __name__ == "__main__":
    opt = parser.parse_args()
    detector = ExtractSIFT(opt.num_kp)
    # get image lists
    search = os.path.join(opt.input_path, opt.img_glob)
    listing = glob.glob(search)

    for img_path in tqdm(listing):
        kp, desc = detector.run(img_path)
        save_path = img_path + '.' + opt.suffix + '.hdf5'
        write_feature(kp, desc, save_path)
