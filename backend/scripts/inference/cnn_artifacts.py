"""Authors' CNNDetection ResNet-50, blur/JPEG augmentation checkpoint."""
import argparse
from pathlib import Path
from common import add_sys_path, cached, checkpoint_id, file_key, probability, revision, run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'weights', 'frames'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args(argv)
    add_sys_path(args.repo.resolve())
    import torch
    from PIL import Image
    from torchvision import transforms
    from networks.resnet import resnet50

    def load():
        model = resnet50(num_classes=1)
        state = torch.load(args.weights, map_location='cpu', weights_only=True)
        model.load_state_dict(state['model'], strict=True)
        model.to(args.device).eval()
        return model

    model = cached(('cnn_artifacts', str(args.repo.resolve()), args.device, file_key(args.weights)), load)
    transform = transforms.Compose([transforms.ToTensor(),
        transforms.Normalize(mean=[.485, .456, .406], std=[.229, .224, .225])])
    samples = []
    for path in sorted(args.frames.glob('frame_*.jpg')):
        with Image.open(path) as image:
            tensor = transform(image.convert('RGB')).unsqueeze(0).to(args.device)
        with torch.inference_mode():
            logits = model(tensor).reshape(-1)
            if logits.numel() != 1:
                raise ValueError('Expected one synthetic-image logit')
            value = probability(torch.sigmoid(logits[0]).item())
        samples.append({'path': path.name, 'fake_probability': value, 'logits': logits.cpu().tolist()})
    return {'samples': samples, 'checkpoint': checkpoint_id(args.weights),
        'model_version': 'CNNDetection@' + revision(args.repo), 'notes': [
            f'Scored {len(samples)} of {len(samples)} sampled frames.',
            'Official demo preprocessing: uncropped RGB frame, ImageNet normalization; sigmoid synthetic-image logit.',
            'ProGAN-trained blur/JPEG-augmented checkpoint. Output screens learned synthesis artifacts; it does not identify the generator.',
            'Video-level mean and 0.5 review rule have not been validated on DPS media.']}


if __name__ == '__main__':
    run(main)
